import json
from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest

from easy_quant.domain.market_data.entities import SemanticRequest
from easy_quant.domain.market_data.fundamentals import FINANCIAL_DATASETS
from easy_quant.infrastructure.data_sources.financial_normalization import normalize_financial
from easy_quant.infrastructure.data_sources.financial_sources import (
    EastMoneyFinancialSource,
    SinaFinancialSource,
)

FIXTURE = json.loads(
    (Path(__file__).parents[1] / "fixtures/financial-v1.json").read_text(encoding="utf-8")
)


def semantic(dataset):
    return SemanticRequest(
        dataset,
        {"symbol": "000001", "start_date": "2025-01-01", "end_date": "2026-09-30"},
        "financial-v1-test",
    )


@pytest.mark.parametrize("dataset", FINANCIAL_DATASETS)
def test_eastmoney_all_direct_endpoints_and_projection(dataset):
    calls = []

    def handler(request):
        calls.append(request)
        path = request.url.path
        if path.endswith("/Index"):
            return httpx.Response(200, text='<input id="hidctype" value="3">')
        if path.endswith("DateAjaxNew"):
            assert request.url.params["companyType"] == "3"
            return httpx.Response(200, json={"data": [{"REPORT_DATE": "2025-12-31"}]})
        if path.endswith("AjaxNew"):
            assert request.url.params["dates"] == "2025-12-31"
            assert request.url.params["reportType"] == "1"
            return httpx.Response(200, json={"data": [FIXTURE["statement"]]})
        if dataset == "business-compositions":
            return httpx.Response(200, json={"zygcfx": [FIXTURE["business"]]})
        fixture = {
            "financial-indicators": "indicators",
            "company-profiles": "profile",
            "dividend-plans": "dividends",
            "shareholder-counts": "holders",
        }[dataset]
        return httpx.Response(
            200,
            json={"success": True, "result": {"data": [FIXTURE[fixture]], "count": 1, "pages": 1}},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        payload, content_type = EastMoneyFinancialSource(client).fetch(semantic(dataset))
    row = json.loads(payload)[0]
    assert content_type == "application/json"
    assert row["symbol"] == "000001" and row["schema_version"] == "financial-v1"
    if dataset == "company-profiles":
        assert row["registered_capital"] == "1234500.00"
        assert "不得缓存" not in payload.decode() and "CHAIRMAN" not in payload.decode()
    if dataset == "business-compositions":
        assert row["revenue_ratio"] == "12.500" and row["gross_margin"] == "50.0"
    if dataset == "financial-indicators":
        assert row["roe"] == "8.07" and row["gross_margin"] is None
    if dataset in EastMoneyFinancialSource.reports:
        assert len(calls) == 3 and row["total_assets"] == "1234567.89"
        assert row["raw_fields"]["BANK_SPECIFIC_ITEM"] == "456.00"


@pytest.mark.parametrize("dataset", SinaFinancialSource.reports)
def test_sina_direct_reports_keep_first_duplicate_field_and_percent_unit(dataset):
    def handler(request):
        assert request.url.params["source"] == SinaFinancialSource.reports[dataset]
        assert request.url.params["paperCode"] == "sz000001"
        return httpx.Response(
            200,
            json={
                "result": {
                    "data": {"report_count": 1, "report_list": {"20251231": FIXTURE["sina"]}}
                }
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        rows = json.loads(SinaFinancialSource(client).fetch(semantic(dataset))[0])
    assert rows[0]["total_assets"] == "1234567.89"
    assert rows[0]["roe"] == "8.070000"
    assert rows[0]["statement_scope"] == "合并"
    assert rows[0]["field_labels"]["TOTASSET"] == "资产总计"
    assert rows[0]["published_at"] == "2026-03-20T23:59:59+08:00"


@pytest.mark.parametrize(
    "payload",
    [
        {"success": False},
        {"success": True, "result": None},
        {"success": True, "result": {"data": [], "count": 1, "pages": 1}},
    ],
)
def test_invalid_or_incomplete_eastmoney_is_failure(payload):
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
        ) as client,
        pytest.raises(ValueError),
    ):
        EastMoneyFinancialSource(client).fetch(semantic("financial-indicators"))


def test_eastmoney_consumes_all_pages_and_rejects_changed_counts():
    calls = []

    def handler(request):
        page = int(request.url.params["p"])
        calls.append(page)
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": {
                    "data": [
                        {
                            **FIXTURE["indicators"],
                            "REPORT_DATE": "2025-12-31" if page == 1 else "2025-09-30",
                        }
                    ],
                    "count": 2,
                    "pages": 2,
                },
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert (
            len(
                json.loads(
                    EastMoneyFinancialSource(client).fetch(semantic("financial-indicators"))[0]
                )
            )
            == 2
        )
    assert calls == [1, 2]


@pytest.mark.parametrize("value", ["NaN", "Infinity", "not-a-number"])
def test_nonfinite_financial_values_never_enter_cache(value):
    with pytest.raises(ValueError):
        normalize_financial(
            "financial-indicators", "000001", {**FIXTURE["indicators"], "ROEJQ": value}
        )


def test_wrong_symbol_fails_but_suspicious_announcement_is_retained_with_warning():
    with pytest.raises(ValueError):
        normalize_financial(
            "financial-indicators", "000001", {**FIXTURE["indicators"], "SECURITY_CODE": "000002"}
        )
    row = normalize_financial(
        "financial-indicators", "000001", {**FIXTURE["indicators"], "NOTICE_DATE": "2025-12-30"}
    )
    assert row["published_at"].startswith("2025-12-30")
    assert "000001" in row["time_warning"]
    dividend = normalize_financial(
        "dividend-plans", "000001", {**FIXTURE["indicators"], "NOTICE_DATE": "2025-12-30"}
    )
    assert "time_warning" not in dividend


@pytest.mark.parametrize("broken", [False, True])
def test_sina_full_pagination_and_count_changes(broken):
    calls = []

    def handler(request):
        page = int(request.url.params["page"])
        calls.append(page)
        offset = 0 if page == 1 else 100
        reports = {
            (date(2000, 1, 1) + timedelta(days=index)).strftime("%Y%m%d"): FIXTURE["sina"]
            for index in range(offset, 100 if page == 1 else 101)
        }
        return httpx.Response(
            200,
            json={
                "result": {
                    "data": {
                        "report_count": 102 if broken and page == 2 else 101,
                        "report_list": reports,
                    }
                }
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        source = SinaFinancialSource(client)
        if broken:
            with pytest.raises(ValueError, match="分页数量"):
                source.fetch(semantic("balance-sheets"))
        else:
            assert len(json.loads(source.fetch(semantic("balance-sheets"))[0])) == 101
    assert calls == [1, 2]


def test_eastmoney_duplicate_pages_are_rejected():
    payload = {"success": True, "result": {"data": [FIXTURE["indicators"]], "count": 2, "pages": 2}}
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
        ) as client,
        pytest.raises(ValueError, match="重复"),
    ):
        EastMoneyFinancialSource(client).fetch(semantic("financial-indicators"))

import json
from pathlib import Path

import httpx
import pytest

from easy_quant.domain.market_data.entities import SemanticRequest
from easy_quant.infrastructure.data_sources.financial_bulk import EastMoneyBulkFinancialSource
from easy_quant.infrastructure.data_sources.financial_sources import EastMoneyFinancialSource

FIXTURE = json.loads(
    (Path(__file__).parents[1] / "fixtures/financial-v1.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize(
    ("dataset", "fixture"),
    [
        ("balance-sheets", "statement"),
        ("income-statements", "statement"),
        ("cash-flow-statements", "statement"),
        ("financial-indicators", "indicators"),
        ("company-profiles", "profile"),
        ("dividend-plans", "dividends"),
        ("shareholder-counts", "holders"),
    ],
)
def test_bulk_contract_projects_known_stocks_and_avoids_per_stock_requests(dataset, fixture):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={"success": True, "result": {"count": 1, "pages": 1, "data": [FIXTURE[fixture]]}},
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        rows, pages, count = EastMoneyBulkFinancialSource(client).page(
            dataset, "2025-12-31", 1, {"000001"}
        )
    assert count == pages == len(rows) == len(requests) == 1
    assert rows[0]["source_format"] == "bulk-v1"
    assert requests[0].url.params["pageSize"] == "500"
    assert "SECUCODE=" not in requests[0].url.params["filter"]
    if dataset in {"dividend-plans", "shareholder-counts"}:
        assert "SECURITY_TYPE_CODE" not in requests[0].url.params["filter"]
    if dataset == "company-profiles":
        assert "ORG_TEL" not in json.dumps(rows) and "ORG_EMAIL" not in json.dumps(rows)


@pytest.mark.parametrize(
    "result",
    [
        {"count": 501, "pages": 2, "data": [FIXTURE["statement"]]},
        {"count": 1, "pages": 2, "data": [FIXTURE["statement"]]},
    ],
)
def test_incomplete_bulk_page_is_rejected_before_persistence(result):
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"success": True, "result": result})
            )
        ) as client,
        pytest.raises(ValueError),
    ):
        EastMoneyBulkFinancialSource(client).page("balance-sheets", "2025-12-31", 1, {"000001"})


def test_invalid_stock_does_not_discard_other_stocks_and_exposes_context():
    rows = [
        FIXTURE["indicators"],
        {**FIXTURE["indicators"], "SECURITY_CODE": "000002", "ROEJQ": "NaN"},
    ]
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, json={"success": True, "result": {"count": 2, "pages": 1, "data": rows}}
            )
        )
    ) as client:
        page = EastMoneyBulkFinancialSource(client).page(
            "financial-indicators", "2025-12-31", 1, {"000001", "000002"}
        )
    assert len(page.rows) == 1
    assert page.failures[0]["symbol"] == "000002"
    assert "2025-12-31" in page.failures[0]["message"]


def test_business_bulk_matches_single_stock_contract_without_creating_metadata_only_versions():
    row = {**FIXTURE["business"], "SECURITY_CODE": "000001", "SECUCODE": "000001.SZ"}
    requests = []

    def handle(request):
        requests.append(request)
        if request.url.path.endswith("PageAjax"):
            return httpx.Response(200, json={"zygcfx": [row]})
        assert request.url.params["reportName"] == "RPT_F10_FN_MAINOP"
        assert request.url.params["filter"] == "(REPORT_DATE='2025-12-31')"
        assert request.url.params["pageSize"] == "500"
        assert request.url.params["sortColumns"] == "SECURITY_CODE,MAINOP_TYPE,ITEM_NAME"
        assert "SECURITY_INNER_CODE" not in request.url.params["columns"]
        return httpx.Response(
            200, json={"success": True, "result": {"count": 1, "pages": 1, "data": [row]}}
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        bulk = EastMoneyBulkFinancialSource(client).page(
            "business-compositions", "2025-12-31", 1, {"000001"}
        )
        direct, _ = EastMoneyFinancialSource(client).fetch(
            SemanticRequest("business-compositions", {"symbol": "000001"}, "id")
        )
    assert bulk.rows == json.loads(direct)
    assert bulk.rows[0]["revenue_ratio"] == "12.500"
    assert bulk.rows[0]["gross_margin"] == "50.0"
    assert len(requests) == 2


def test_business_can_split_one_stock_across_pages_and_keep_all_categories():
    rows = [
        {**FIXTURE["business"], "SECURITY_CODE": "000001", "ITEM_NAME": f"项目{i:03d}"}
        for i in range(501)
    ]

    def handle(request):
        page = int(request.url.params["pageNumber"])
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": {"count": 501, "pages": 2, "data": rows[(page - 1) * 500 : page * 500]},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        source = EastMoneyBulkFinancialSource(client)
        pages = [source.page("business-compositions", "2025-12-31", p, {"000001"}) for p in (1, 2)]
    assert [len(p.rows) for p in pages] == [500, 1]
    assert len({row["item_name"] for page in pages for row in page.rows}) == 501

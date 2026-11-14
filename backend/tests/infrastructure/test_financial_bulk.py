import json
from pathlib import Path

import httpx
import pytest

from easy_quant.infrastructure.data_sources.financial_bulk import EastMoneyBulkFinancialSource

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

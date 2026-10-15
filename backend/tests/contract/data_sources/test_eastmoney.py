import json

import httpx
import pytest

from easy_quant.domain.market_data.entities import SemanticRequest
from easy_quant.infrastructure.data_sources.eastmoney.adapters import EastMoneySource
from easy_quant.infrastructure.data_sources.eastmoney.client import EastMoneyClient


def test_eastmoney_adapter_uses_injected_transport() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"data": {"total": 0, "diff": []}})
    )
    with httpx.Client(transport=transport) as client:
        payload, media_type = EastMoneySource(EastMoneyClient(client)).fetch(
            SemanticRequest("securities", {"pn": 1}, "id")
        )
    assert b'"total": 0' in payload
    assert media_type == "application/json"


def test_eastmoney_daily_bars_map_adjustment_to_fqt() -> None:
    seen = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params["fqt"])
        return httpx.Response(200, json={"data": {"klines": []}})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        source = EastMoneySource(EastMoneyClient(client))
        for adjustment in ("none", "qfq"):
            source.fetch(
                SemanticRequest(
                    "daily-bars",
                    {
                        "symbol": "000016",
                        "start_date": "2026-09-03",
                        "end_date": "2026-09-30",
                        "adjustment": adjustment,
                    },
                    adjustment,
                )
            )
    assert seen == ["0", "1"]


def test_live_quotes_request_only_selected_symbols():
    seen = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, json={"data": {"diff": []}})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        EastMoneySource(EastMoneyClient(client)).fetch(
            SemanticRequest("live-quotes", {"symbols": ["000001", "600001"]}, "q")
        )
    assert seen[0].path == "/api/qt/ulist.np/get"
    assert seen[0].params["secids"] == "0.000001,1.600001"
    assert "fs" not in seen[0].params


def test_suspensions_read_all_pages_and_only_confirm_full_day_evidence():
    seen = []
    rows = [
        {
            "SECURITY_CODE": "600293",
            "SUSPEND_START_TIME": "2026-09-29 09:30:00",
            "SUSPEND_END_TIME": None,
            "SUSPEND_EXPIRE": "连续停牌",
        },
        {
            "SECURITY_CODE": "601059",
            "SUSPEND_START_TIME": "2026-09-15 09:30:00",
            "SUSPEND_END_TIME": "2026-10-16 15:00:00",
        },
        {
            "SECURITY_CODE": "600001",
            "SUSPEND_START_TIME": "2026-09-30 10:00:00",
            "SUSPEND_END_TIME": "2026-09-30 11:00:00",
        },
        {
            "SECURITY_CODE": "600002",
            "SUSPEND_START_TIME": "2026-09-01 09:30:00",
            "SUSPEND_END_TIME": "2026-09-29 15:00:00",
        },
    ]

    def respond(request):
        seen.append(request.url)
        page = int(request.url.params["pageNumber"])
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": {"pages": 2, "count": 4, "data": rows[(page - 1) * 2 : page * 2]},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        payload, _ = EastMoneySource(EastMoneyClient(client)).fetch(
            SemanticRequest("trading-status", {"end_day": "2026-09-30"}, "status")
        )
    assert len(seen) == 2
    assert seen[0].params["filter"] == "(MARKET=\"全部\")(DATETIME='2026-09-30')"
    assert [row["symbol"] for row in json.loads(payload)] == ["600293", "601059"]
    assert all(row["as_of_day"] == "2026-09-30" for row in json.loads(payload))
    assert json.loads(payload)[0]["suspension_start"] == "2026-09-29T09:30:00+08:00"


@pytest.mark.parametrize(
    "response",
    [
        {"success": False, "result": None},
        {"success": True, "result": {"pages": 1, "count": 1, "data": []}},
    ],
)
def test_invalid_suspension_feed_is_not_treated_as_empty_success(response):
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response))
        ) as client,
        pytest.raises(ValueError),
    ):
        EastMoneySource(EastMoneyClient(client)).fetch(
            SemanticRequest("trading-status", {"end_day": "2026-09-30"}, "status")
        )

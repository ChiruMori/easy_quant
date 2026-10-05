import httpx

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

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

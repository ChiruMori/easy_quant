import json

import httpx
import pytest

from easy_quant.application.services.market_data_sync import validate_live_quote_response
from easy_quant.domain.market_data.entities import SemanticRequest
from easy_quant.infrastructure.data_sources.tencent.quotes import TencentQuoteSource


def test_tencent_quotes_only_requested_symbols_with_stock_index_and_beijing_identity():
    seen = []

    def respond(request):
        seen.append(str(request.url))
        text = "\n".join(
            f'v_{identifier}="51~样本~{identifier[2:]}~10.25~0~0";'
            for identifier in ["sz000001", "sh600000", "bj920001", "sh000001"]
        )
        return httpx.Response(200, content=text.encode("gb18030"))

    request = SemanticRequest(
        "live-quotes", {"symbols": ["000001", "600000", "920001", "sh000001"]}, "q"
    )
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        payload, _ = TencentQuoteSource(client).fetch(request)
    validate_live_quote_response(request, payload)
    assert {row["code"] for row in json.loads(payload)} == {
        "000001",
        "600000",
        "920001",
        "sh000001",
    }
    assert seen == ["https://qt.gtimg.cn/q=bj920001,sh000001,sh600000,sz000001"]


@pytest.mark.parametrize(
    "response", [b'v_sz000001="";', b'v_sz000001="51~sample~000002~10";', b'v_pv_none_match="1";']
)
def test_incomplete_or_mismatched_tencent_response_is_rejected(response):
    request = SemanticRequest("live-quotes", {"symbols": ["000001"]}, "q")
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, content=response))
        ) as client,
        pytest.raises(ValueError),
    ):
        payload, _ = TencentQuoteSource(client).fetch(request)
        validate_live_quote_response(request, payload)

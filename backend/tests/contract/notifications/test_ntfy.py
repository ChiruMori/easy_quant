from email.header import decode_header, make_header

import httpx
import pytest

from easy_quant.application.ports.notifications import (
    PermanentDeliveryError,
    TemporaryDeliveryError,
)
from easy_quant.domain.notifications.entities import ChannelType, NotificationSubscription
from easy_quant.infrastructure.notifications.ntfy import NtfyChannel


def test_ntfy_full_url_and_chinese_title_are_supported_offline():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"id": "test"})

    channel = NtfyChannel(httpx.Client(transport=httpx.MockTransport(handler)))
    channel.send(
        NotificationSubscription("s", "u", ChannelType.NTFY, "https://push.example.test/topic"),
        "实盘连通性测试",
        "测试内容",
        "key",
    )
    assert str(requests[0].url) == "https://push.example.test/topic"
    assert str(make_header(decode_header(requests[0].headers["Title"]))) == "实盘连通性测试"
    assert requests[0].content.decode() == "测试内容"


@pytest.mark.parametrize("status", [302, 400, 403, 429, 503])
def test_ntfy_non_success_is_never_reported_as_delivered(status):
    channel = NtfyChannel(
        httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(status)))
    )
    error_type = TemporaryDeliveryError if status in {429, 503} else PermanentDeliveryError
    with pytest.raises(error_type) as raised:
        channel.send(
            NotificationSubscription("s", "u", ChannelType.NTFY, "fixture-topic"),
            "title",
            "body",
            "event-key",
        )
    assert raised.value.code == f"ntfy_http_{status}"

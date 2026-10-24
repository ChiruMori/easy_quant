import base64
import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime
from urllib.parse import parse_qs

import httpx
import pytest

from easy_quant.application.ports.notifications import (
    PermanentDeliveryError,
    TemporaryDeliveryError,
)
from easy_quant.application.services.notification_targets import validate_notification_target
from easy_quant.domain.notifications.entities import ChannelType, NotificationSubscription
from easy_quant.domain.shared.errors import ValidationError
from easy_quant.infrastructure.notifications.bot_webhooks import BotWebhookChannel
from tests.fakes.core import FixedClock

URLS = {
    "dingtalk": "https://oapi.dingtalk.com/robot/send?access_token=fixture-token",
    "feishu": "https://open.feishu.cn/open-apis/bot/v2/hook/fixture-hook",
    "wecom": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=fixture-key",
}
CLOCK = FixedClock(datetime(2026, 9, 29, 8, tzinfo=UTC))


@pytest.mark.parametrize("kind", list(URLS))
def test_protocol_signatures_and_redacted_http_logs(kind, caplog):
    requests = []

    def send(request):
        requests.append(request)
        return httpx.Response(200, json={"code": 0} if kind == "feishu" else {"errcode": 0})

    channel = BotWebhookChannel(httpx.Client(transport=httpx.MockTransport(send)), CLOCK)
    secret = "fixture-signing-secret" if kind != "wecom" else None
    with caplog.at_level(logging.INFO, logger="httpx"):
        channel.send(
            NotificationSubscription(
                "s", "u", ChannelType(kind), URLS[kind], signing_secret=secret
            ),
            "策略建议",
            "同轮三条信号",
            "event",
        )
    assert len(requests) == 1
    request = requests[0]
    assert request.headers["Idempotency-Key"] == "event"
    data = json.loads(request.content)
    content = data["content"]["text"] if kind == "feishu" else data["text"]["content"]
    assert content == "Easy Quant · 策略建议\n同轮三条信号"
    assert "fixture-token" not in caplog.text and "fixture-hook" not in caplog.text
    assert "fixture-key" not in caplog.text and "fixture-signing-secret" not in caplog.text
    if kind == "dingtalk":
        assert secret is not None
        params = parse_qs(request.url.query.decode())
        ts = str(int(CLOCK.now().timestamp()) * 1000)
        assert params["timestamp"] == [ts]
        assert params["sign"] == [
            base64.b64encode(
                hmac.new(secret.encode(), f"{ts}\n{secret}".encode(), hashlib.sha256).digest()
            ).decode()
        ]
    if kind == "feishu":
        ts = str(int(CLOCK.now().timestamp()))
        assert data["timestamp"] == ts
        assert (
            data["sign"]
            == base64.b64encode(
                hmac.new(f"{ts}\n{secret}".encode(), b"", hashlib.sha256).digest()
            ).decode()
        )


@pytest.mark.parametrize(
    "kind,status,body,error",
    [
        ("dingtalk", 200, {"errcode": 310000, "errmsg": "fixture-token"}, PermanentDeliveryError),
        ("feishu", 200, {"code": 11232}, TemporaryDeliveryError),
        ("wecom", 200, {"errcode": 45009}, TemporaryDeliveryError),
        ("wecom", 200, {"errcode": 93000}, PermanentDeliveryError),
        ("feishu", 200, {}, TemporaryDeliveryError),
        ("wecom", 200, {"errcode": True}, TemporaryDeliveryError),
        ("dingtalk", 429, {}, TemporaryDeliveryError),
        ("feishu", 503, {}, TemporaryDeliveryError),
        ("wecom", 302, {}, PermanentDeliveryError),
    ],
)
def test_business_http_failures_are_typed_and_do_not_expose_credentials(kind, status, body, error):
    adapter = BotWebhookChannel(
        httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(status, json=body))),
        CLOCK,
    )
    with pytest.raises(error) as raised:
        adapter.send(
            NotificationSubscription("s", "u", ChannelType(kind), URLS[kind]), "标题", "正文", "key"
        )
    assert "fixture-token" not in str(raised.value)


@pytest.mark.parametrize(
    "url",
    [
        "http://oapi.dingtalk.com/robot/send?access_token=x",
        "https://oapi.dingtalk.com.evil.invalid/robot/send?access_token=x",
        "https://oapi.dingtalk.com/other?access_token=x",
        "https://127.0.0.1/robot/send?access_token=x",
        "https://oapi.dingtalk.com:444/robot/send?access_token=x",
    ],
)
def test_bot_url_contract_rejects_wrong_endpoints(url):
    with pytest.raises(ValidationError):
        validate_notification_target("dingtalk", url)


def test_wecom_long_unicode_message_is_truncated_once_with_notice():
    messages = []

    def send(request):
        messages.append(json.loads(request.content)["text"]["content"])
        return httpx.Response(200, json={"errcode": 0})

    adapter = BotWebhookChannel(httpx.Client(transport=httpx.MockTransport(send)), CLOCK)
    adapter.send(
        NotificationSubscription("s", "u", ChannelType.WECOM, URLS["wecom"]),
        "标题",
        "股" * 3000,
        "k",
    )
    assert len(messages) == 1 and len(messages[0].encode()) <= 2048
    assert messages[0].endswith("请前往平台查看完整建议。")

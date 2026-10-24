from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from easy_quant.application.ports.core import Clock
from easy_quant.application.ports.notifications import (
    PermanentDeliveryError,
    TemporaryDeliveryError,
)
from easy_quant.application.services.notification_targets import validate_notification_target
from easy_quant.domain.notifications.entities import NotificationSubscription
from easy_quant.domain.shared.errors import ValidationError


class BotUrlFilter(logging.Filter):
    def filter(self, record):
        record.msg = re.sub(
            r"https://(?:oapi\.dingtalk\.com|open\.feishu\.cn|qyapi\.weixin\.qq\.com)[^\s\"']*",
            "[robot-webhook]",
            record.getMessage(),
        )
        record.args = ()
        return True


class BotWebhookChannel:
    def __init__(self, client: httpx.Client, clock: Clock):
        self.client, self.clock = client, clock
        logger = logging.getLogger("httpx")
        if not any(isinstance(item, BotUrlFilter) for item in logger.filters):
            logger.addFilter(BotUrlFilter())

    def send(
        self, subscription: NotificationSubscription, title: str, body: str, idempotency_key: str
    ) -> None:
        channel = subscription.channel.value
        secret = subscription.signing_secret or ""
        try:
            validate_notification_target(channel, subscription.destination, secret)
        except ValidationError:
            raise PermanentDeliveryError("机器人地址配置无效", "bot_configuration") from None
        text = f"{title if title.startswith('Easy Quant') else 'Easy Quant · ' + title}\n{body}"
        limit = 2048 if channel == "wecom" else 18000
        if len(text.encode()) > limit:
            suffix = "\n…内容过长，请前往平台查看完整建议。"
            text = (
                text.encode()[: limit - len(suffix.encode())].decode("utf-8", errors="ignore")
                + suffix
            )
        url = subscription.destination.strip()
        payload: dict = (
            {"msg_type": "text", "content": {"text": text}}
            if channel == "feishu"
            else {"msgtype": "text", "text": {"content": text}}
        )
        if secret:
            seconds = int(self.clock.now().timestamp())
            if channel == "dingtalk":
                timestamp = str(seconds * 1000)
                sign = base64.b64encode(
                    hmac.new(
                        secret.encode(), f"{timestamp}\n{secret}".encode(), hashlib.sha256
                    ).digest()
                ).decode()
                parts = urlsplit(url)
                query = parse_qsl(parts.query) + [("timestamp", timestamp), ("sign", sign)]
                url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
            elif channel == "feishu":
                timestamp = str(seconds)
                sign = base64.b64encode(
                    hmac.new(f"{timestamp}\n{secret}".encode(), b"", hashlib.sha256).digest()
                ).decode()
                payload.update(timestamp=timestamp, sign=sign)
        try:
            response = self.client.post(
                url,
                json=payload,
                follow_redirects=False,
                headers={"Idempotency-Key": idempotency_key},
            )
        except httpx.TransportError:
            raise TemporaryDeliveryError("机器人服务暂时不可用", f"{channel}_transport") from None
        if response.status_code == 429 or response.status_code >= 500:
            raise TemporaryDeliveryError("机器人服务繁忙", f"{channel}_http_{response.status_code}")
        if not 200 <= response.status_code < 300:
            raise PermanentDeliveryError(
                "机器人请求被拒绝", f"{channel}_http_{response.status_code}"
            )
        try:
            result = response.json()
            code = (
                result.get("code", result.get("StatusCode"))
                if channel == "feishu"
                else result.get("errcode")
            )
            if not isinstance(code, int) or isinstance(code, bool):
                raise ValueError
        except (ValueError, AttributeError):
            raise TemporaryDeliveryError(
                "机器人返回无效响应", f"{channel}_invalid_response"
            ) from None
        if code == 0:
            return
        if code in {11232, 45009, 45033, -1, 130101}:
            raise TemporaryDeliveryError("机器人服务限流或繁忙", f"{channel}_code_{code}")
        raise PermanentDeliveryError("机器人配置或消息被拒绝", f"{channel}_code_{code}")

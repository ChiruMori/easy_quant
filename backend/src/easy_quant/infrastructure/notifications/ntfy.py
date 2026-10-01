from __future__ import annotations

import httpx

from easy_quant.application.ports.notifications import (
    PermanentDeliveryError,
    TemporaryDeliveryError,
)
from easy_quant.domain.notifications.entities import NotificationSubscription


class NtfyChannel:
    def __init__(self, client: httpx.Client, base_url: str = "https://ntfy.sh") -> None:
        self.client, self.base_url = client, base_url.rstrip("/")

    def send(
        self, subscription: NotificationSubscription, title: str, body: str, idempotency_key: str
    ) -> None:
        try:
            response = self.client.post(
                f"{self.base_url}/{subscription.destination}",
                content=body.encode(),
                headers={"Title": title, "Idempotency-Key": idempotency_key},
            )
        except httpx.TransportError as error:
            raise TemporaryDeliveryError("ntfy 暂时不可用") from error
        if response.status_code >= 500 or response.status_code == 429:
            raise TemporaryDeliveryError(f"ntfy 临时错误 {response.status_code}")
        if response.status_code >= 400:
            raise PermanentDeliveryError(f"ntfy 配置错误 {response.status_code}")

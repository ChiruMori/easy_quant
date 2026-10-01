from __future__ import annotations

from typing import Protocol

from easy_quant.domain.notifications.entities import NotificationDelivery, NotificationSubscription


class TemporaryDeliveryError(RuntimeError):
    pass


class PermanentDeliveryError(RuntimeError):
    pass


class NotificationChannel(Protocol):
    def send(
        self, subscription: NotificationSubscription, title: str, body: str, idempotency_key: str
    ) -> None: ...


class DeliveryRepository(Protocol):
    def get_by_key(self, idempotency_key: str) -> NotificationDelivery | None: ...
    def add(self, delivery: NotificationDelivery) -> None: ...
    def save(self, delivery: NotificationDelivery) -> None: ...

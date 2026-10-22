from __future__ import annotations

from typing import Protocol

from easy_quant.domain.notifications.entities import NotificationDelivery, NotificationSubscription


class TemporaryDeliveryError(RuntimeError):
    def __init__(self, message: str, code: str = "temporary_failure"):
        super().__init__(message)
        self.code = code


class PermanentDeliveryError(RuntimeError):
    def __init__(self, message: str, code: str = "permanent_failure"):
        super().__init__(message)
        self.code = code


class NotificationChannel(Protocol):
    def send(
        self, subscription: NotificationSubscription, title: str, body: str, idempotency_key: str
    ) -> None: ...


class DeliveryRepository(Protocol):
    def get_by_key(self, idempotency_key: str) -> NotificationDelivery | None: ...
    def add(self, delivery: NotificationDelivery) -> None: ...
    def save(self, delivery: NotificationDelivery) -> None: ...

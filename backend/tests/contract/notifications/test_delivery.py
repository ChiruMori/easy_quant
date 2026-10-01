import pytest

from easy_quant.application.ports.notifications import (
    PermanentDeliveryError,
    TemporaryDeliveryError,
)
from easy_quant.application.services.notification_delivery import NotificationDeliveryService
from easy_quant.domain.notifications.entities import (
    ChannelType,
    DeliveryStatus,
    NotificationDelivery,
    NotificationSubscription,
)
from tests.fakes.core import SequentialIdGenerator


class Repository:
    def __init__(self) -> None:
        self.items: dict[str, NotificationDelivery] = {}

    def get_by_key(self, idempotency_key: str) -> NotificationDelivery | None:
        return self.items.get(idempotency_key)

    def add(self, delivery: NotificationDelivery) -> None:
        self.items[delivery.idempotency_key] = delivery

    def save(self, delivery: NotificationDelivery) -> None:
        self.items[delivery.idempotency_key] = delivery


class Channel:
    def __init__(self, error: Exception | None = None) -> None:
        self.error, self.calls = error, 0

    def send(
        self,
        subscription: NotificationSubscription,
        title: str,
        body: str,
        idempotency_key: str,
    ) -> None:
        self.calls += 1
        if self.error:
            raise self.error


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (None, DeliveryStatus.DELIVERED),
        (TemporaryDeliveryError("later"), DeliveryStatus.RETRY),
        (PermanentDeliveryError("bad"), DeliveryStatus.FAILED),
    ],
)
def test_delivery_outcomes_and_idempotency(error, status) -> None:
    repository, channel = Repository(), Channel(error)
    service = NotificationDeliveryService(repository, {"email": channel}, SequentialIdGenerator())
    subscription = NotificationSubscription("s", "u", ChannelType.EMAIL, "u@example.test")
    result = service.deliver("r", subscription, "title", "body")
    assert result.status is status
    if status is DeliveryStatus.DELIVERED:
        service.deliver("r", subscription, "title", "body")
        assert channel.calls == 1

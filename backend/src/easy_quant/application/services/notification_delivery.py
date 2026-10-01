from __future__ import annotations

import hashlib

from easy_quant.application.ports.core import IdGenerator
from easy_quant.application.ports.notifications import (
    DeliveryRepository,
    NotificationChannel,
    PermanentDeliveryError,
    TemporaryDeliveryError,
)
from easy_quant.domain.notifications.entities import (
    DeliveryStatus,
    NotificationDelivery,
    NotificationSubscription,
)


class NotificationDeliveryService:
    def __init__(
        self,
        repository: DeliveryRepository,
        channels: dict[str, NotificationChannel],
        ids: IdGenerator,
    ) -> None:
        self.repository, self.channels, self.ids = repository, channels, ids

    def deliver(
        self, recommendation_id: str, subscription: NotificationSubscription, title: str, body: str
    ) -> NotificationDelivery:
        key = hashlib.sha256(
            f"{recommendation_id}|{subscription.id}|{subscription.channel}".encode()
        ).hexdigest()
        existing = self.repository.get_by_key(key)
        if existing and existing.status is DeliveryStatus.DELIVERED:
            return existing
        delivery = existing or NotificationDelivery(
            self.ids.new(), recommendation_id, subscription.id, subscription.channel, key
        )
        if existing is None:
            self.repository.add(delivery)
        delivery.attempts += 1
        try:
            self.channels[subscription.channel.value].send(subscription, title, body, key)
            delivery.status, delivery.error = DeliveryStatus.DELIVERED, None
        except TemporaryDeliveryError as error:
            delivery.status, delivery.error = DeliveryStatus.RETRY, str(error)
        except PermanentDeliveryError as error:
            delivery.status, delivery.error = DeliveryStatus.FAILED, str(error)
        self.repository.save(delivery)
        return delivery

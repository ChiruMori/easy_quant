from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ChannelType(StrEnum):
    EMAIL = "email"
    NTFY = "ntfy"


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    RETRY = "retry"
    FAILED = "failed"


@dataclass(slots=True)
class NotificationSubscription:
    id: str
    owner_id: str
    channel: ChannelType
    destination: str
    enabled: bool = True


@dataclass(slots=True)
class NotificationDelivery:
    id: str
    recommendation_id: str
    subscription_id: str
    channel: ChannelType
    idempotency_key: str
    status: DeliveryStatus = DeliveryStatus.PENDING
    attempts: int = 0
    error: str | None = None

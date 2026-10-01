from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Any

from easy_quant.application.ports.notifications import (
    PermanentDeliveryError,
    TemporaryDeliveryError,
)
from easy_quant.domain.notifications.entities import ChannelType, NotificationSubscription
from easy_quant.domain.scheduling.entities import Job
from easy_quant.infrastructure.core import UuidGenerator


def notify_owner(
    container: Any, owner_id: str, event_id: str, title: str, body: str
) -> list[dict[str, object]]:
    """投递业务事件；业务键保证重复分析不会重复发送。"""

    created: list[dict[str, object]] = []
    for row in container.state.subscriptions:
        if row["owner_id"] != owner_id or not row.get("enabled", True):
            continue
        key = hashlib.sha256(f"{event_id}|{row['id']}".encode()).hexdigest()
        existing = next(
            (item for item in container.state.deliveries if item["idempotency_key"] == key), None
        )
        if existing is not None:
            created.append(existing)
            continue
        channel_name = str(row["channel"])
        delivery: dict[str, object] = {
            "id": f"delivery-{UuidGenerator().new()}",
            "owner_id": owner_id,
            "event_id": event_id,
            "subscription_id": row["id"],
            "channel": channel_name,
            "idempotency_key": key,
            "status": "pending",
            "attempts": 1,
            "title": title,
            "body": body,
        }
        channel = container.notification_channels.get(channel_name)
        if channel is None:
            delivery.update(status="failed", error="通知渠道未配置")
        else:
            try:
                if container.secret_box is None:
                    raise RuntimeError("通知凭据加密器未配置")
                destination = container.secret_box.decrypt(str(row["destination_encrypted"]))
                subscription = NotificationSubscription(
                    str(row["id"]), owner_id, ChannelType(channel_name), destination, True
                )
                channel.send(subscription, title, body, key)
                delivery["status"] = "delivered"
            except TemporaryDeliveryError as error:
                delivery.update(status="retry", error=str(error))
                if container.jobs is not None:
                    now = container.authentication.clock.now()
                    container.jobs.enqueue(
                        Job(
                            UuidGenerator().new(),
                            "notification-delivery",
                            f"notification:{key}",
                            {"delivery_id": delivery["id"]},
                            now + timedelta(minutes=5),
                        )
                    )
            except PermanentDeliveryError as error:
                delivery.update(status="failed", error=str(error))
            except Exception as error:
                delivery.update(status="failed", error=str(error))
        container.state.deliveries.append(delivery)
        created.append(delivery)
    return created

from __future__ import annotations

import hashlib
import logging
from datetime import timedelta
from typing import Any

from easy_quant.application.ports.notifications import (
    PermanentDeliveryError,
    TemporaryDeliveryError,
)
from easy_quant.domain.notifications.entities import ChannelType, NotificationSubscription
from easy_quant.domain.scheduling.entities import Job
from easy_quant.infrastructure.core import UuidGenerator

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3


def _enqueue_recovery(container, delivery):
    if container.jobs is not None:
        attempt = int(delivery.get("attempts", 0)) + 1
        container.jobs.enqueue(
            Job(
                UuidGenerator().new(),
                "notification-delivery",
                f"notification:{delivery['idempotency_key']}:{attempt}",
                {"delivery_id": delivery["id"]},
                container.authentication.clock.now() + timedelta(minutes=5),
            )
        )


def attempt_delivery(container: Any, delivery_id: str, *, recover: bool = False):
    # 先安排恢复任务；发送中进程退出也能从持久记录恢复，外部 I/O 不占用记账锁。
    with container.live_tracking.transaction() as state:
        current = next((dict(row) for row in state.deliveries if row["id"] == delivery_id), None)
    if current is None:
        return {"id": delivery_id, "status": "skipped"}
    if current["status"] in {"delivered", "failed", "skipped"}:
        return current
    if current["status"] in {"sending", "retry"} and not recover:
        return current
    _enqueue_recovery(container, current)
    with container.live_tracking.transaction() as state:
        found = next(
            (
                (index, dict(row))
                for index, row in enumerate(state.deliveries)
                if row["id"] == delivery_id
            ),
            None,
        )
        if found is None:
            return {"id": delivery_id, "status": "skipped"}
        index, delivery = found
        if delivery["status"] in {"delivered", "failed", "skipped"} or (
            delivery["status"] in {"sending", "retry"} and not recover
        ):
            return delivery
        if int(delivery.get("attempts", 0)) >= MAX_ATTEMPTS:
            delivery.update(
                status="failed",
                error="达到最大投递次数，请检查渠道配置",
                error_code="retry_exhausted",
                updated_at=container.authentication.clock.now().isoformat(),
            )
            state.deliveries[index] = delivery
            return delivery
        delivery.update(
            status="sending",
            attempts=int(delivery.get("attempts", 0)) + 1,
            last_attempt_at=container.authentication.clock.now().isoformat(),
            updated_at=container.authentication.clock.now().isoformat(),
        )
        state.deliveries[index] = delivery
    subscription = next(
        (
            row
            for row in container.state.subscriptions
            if row["id"] == delivery["subscription_id"] and row["owner_id"] == delivery["owner_id"]
        ),
        None,
    )
    channel = container.notification_channels.get(str(delivery["channel"]))
    try:
        if subscription is None or not subscription.get("enabled", True):
            raise PermanentDeliveryError("通知渠道已删除或停用", "channel_disabled")
        if channel is None:
            raise PermanentDeliveryError("通知渠道未配置", "channel_unconfigured")
        if container.secret_box is None:
            raise PermanentDeliveryError("通知凭据不可解密", "credentials_unavailable")
        try:
            destination = container.secret_box.decrypt(str(subscription["destination_encrypted"]))
        except Exception:
            raise PermanentDeliveryError("通知凭据不可解密", "credentials_unavailable") from None
        channel.send(
            NotificationSubscription(
                str(subscription["id"]),
                str(delivery["owner_id"]),
                ChannelType(str(delivery["channel"])),
                destination,
                True,
            ),
            str(delivery["title"]),
            str(delivery["body"]),
            str(delivery["idempotency_key"]),
        )
        delivery.update(
            status="delivered",
            error=None,
            error_code=None,
            delivered_at=container.authentication.clock.now().isoformat(),
        )
    except TemporaryDeliveryError as error:
        delivery.update(
            status="retry", error="通知服务暂时不可用，将自动重试", error_code=error.code
        )
    except PermanentDeliveryError as error:
        messages = {
            "channel_disabled": "通知渠道已删除或停用",
            "channel_unconfigured": "通知渠道未配置",
            "credentials_unavailable": "通知凭据不可解密",
        }
        delivery.update(
            status="failed",
            error=messages.get(error.code, "通知服务拒绝请求，请检查渠道配置"),
            error_code=error.code,
        )
    except Exception:
        delivery.update(
            status="failed", error="通知投递失败，请检查渠道配置", error_code="unexpected_failure"
        )
    delivery["updated_at"] = container.authentication.clock.now().isoformat()
    with container.live_tracking.transaction() as state:
        index = next(
            (index for index, row in enumerate(state.deliveries) if row["id"] == delivery_id), None
        )
        if index is not None:
            state.deliveries[index] = delivery
    logger.info(
        "通知投递 delivery_id=%s event_id=%s status=%s error_code=%s",
        delivery_id,
        delivery["event_id"],
        delivery["status"],
        delivery.get("error_code"),
    )
    return delivery


def notify_owner(
    container: Any,
    owner_id: str,
    event_id: str,
    title: str,
    body: str,
    subscription_ids: list[str] | None = None,
    live_instance_id: str | None = None,
) -> list[dict[str, object]]:
    selected = [
        row
        for row in container.state.subscriptions
        if row["owner_id"] == owner_id
        and row.get("enabled", True)
        and (subscription_ids is None or row["id"] in subscription_ids)
    ]
    destinations = selected or [{"id": "no-channel", "channel": "none"}]
    results = []
    for subscription in destinations:
        key = hashlib.sha256(f"{event_id}|{subscription['id']}".encode()).hexdigest()
        with container.live_tracking.transaction() as state:
            delivery = next(
                (dict(row) for row in state.deliveries if row["idempotency_key"] == key), None
            )
            if delivery is None:
                now = container.authentication.clock.now().isoformat()
                delivery = {
                    "id": f"delivery-{UuidGenerator().new()}",
                    "owner_id": owner_id,
                    "event_id": event_id,
                    "live_instance_id": live_instance_id,
                    "subscription_id": subscription["id"],
                    "channel": subscription["channel"],
                    "idempotency_key": key,
                    "title": title,
                    "body": body,
                    "created_at": now,
                    "updated_at": now,
                    "attempts": 0,
                    "status": "pending" if selected else "skipped",
                    "error_code": None if selected else "no_enabled_channel",
                    "error": None if selected else "没有本人启用且被此实盘选中的通知渠道",
                }
                state.deliveries.append(delivery)
        results.append(attempt_delivery(container, str(delivery["id"])))
    return results

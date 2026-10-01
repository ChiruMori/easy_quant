from easy_quant.domain.scheduling.entities import Job
from easy_quant.worker.registry import JobHandlerRegistry


def register_notification_handlers(registry: JobHandlerRegistry, container=None) -> None:
    def deliver(job: Job) -> dict[str, object]:
        if container is not None:
            delivery_id = str(job.payload["delivery_id"])
            deliveries = container.state.deliveries
            index = next(
                index for index, item in enumerate(deliveries) if item["id"] == delivery_id
            )
            delivery = deliveries[index]
            subscription = next(
                item
                for item in container.state.subscriptions
                if item["id"] == delivery["subscription_id"]
            )
            channel = container.notification_channels[str(subscription["channel"])]
            from easy_quant.domain.notifications.entities import (
                ChannelType,
                NotificationSubscription,
            )

            destination = container.secret_box.decrypt(subscription["destination_encrypted"])
            channel.send(
                NotificationSubscription(
                    subscription["id"],
                    subscription["owner_id"],
                    ChannelType(subscription["channel"]),
                    destination,
                ),
                delivery["title"],
                delivery["body"],
                delivery["idempotency_key"],
            )
            delivery.update(status="delivered", error=None, attempts=int(delivery["attempts"]) + 1)
            deliveries[index] = delivery
            return {"delivery_id": delivery_id, "status": "delivered"}
        return {"delivery": job.payload}

    registry.register("notification.deliver", deliver)
    registry.register("notification-delivery", deliver)

from easy_quant.application.services.notification_runtime import attempt_delivery
from easy_quant.domain.scheduling.entities import Job
from easy_quant.worker.registry import JobHandlerRegistry


def register_notification_handlers(registry: JobHandlerRegistry, container=None) -> None:
    def deliver(job: Job) -> dict[str, object]:
        if container is None:
            return {"delivery": job.payload}
        result = attempt_delivery(container, str(job.payload["delivery_id"]), recover=True)
        return {"delivery_id": result["id"], "status": result["status"]}

    registry.register("notification.deliver", deliver)
    registry.register("notification-delivery", deliver)

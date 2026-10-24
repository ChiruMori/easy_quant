import logging

from easy_quant.application.services.live_runtime import analyze_live_instance
from easy_quant.domain.scheduling.entities import Job
from easy_quant.worker.registry import JobHandlerRegistry


def register_live_handlers(registry: JobHandlerRegistry, container=None) -> None:
    def analyze(job: Job) -> dict[str, object]:
        if container is not None:
            identifier = str(job.payload["instance_id"])
            instance = container.state.live_instances.get(identifier)
            name = (instance or {}).get("name") or job.payload.get("live_name") or identifier
            job.payload["live_name"] = name
            logging.getLogger(__name__).info(
                "实盘分析 job_id=%s live_instance_id=%s live_name=%r phase=%s",
                job.id,
                identifier,
                name,
                job.payload.get("phase"),
            )
            context = {"live_instance_id": identifier, "live_name": name}
            if instance is None or instance.get("status") != "active":
                return {**context, "skipped": "实盘未运行", "phase": job.payload.get("phase")}
            return {
                **context,
                **analyze_live_instance(
                    container,
                    str(job.payload["instance_id"]),
                    str(job.payload["phase"]),
                    container.authentication.clock.now(),
                ),
            }
        return {"analyzed": job.payload}

    registry.register("live.analyze", analyze)
    registry.register("live-analysis", analyze)

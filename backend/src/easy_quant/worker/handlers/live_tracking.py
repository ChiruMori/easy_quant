from easy_quant.application.services.live_runtime import analyze_live_instance
from easy_quant.domain.scheduling.entities import Job
from easy_quant.worker.registry import JobHandlerRegistry


def register_live_handlers(registry: JobHandlerRegistry, container=None) -> None:
    def analyze(job: Job) -> dict[str, object]:
        if container is not None:
            return analyze_live_instance(
                container,
                str(job.payload["instance_id"]),
                str(job.payload["phase"]),
                container.authentication.clock.now(),
            )
        return {"analyzed": job.payload}

    registry.register("live.analyze", analyze)
    registry.register("live-analysis", analyze)

from easy_quant.domain.scheduling.entities import Job
from easy_quant.worker.registry import JobHandlerRegistry


def register_backtest_handlers(registry: JobHandlerRegistry) -> None:
    def execute(job: Job) -> dict[str, object]:
        if job.payload.get("cancelled"):
            return {"status": "cancelled"}
        return {"status": "succeeded", "progress": 100}

    registry.register("backtest.run", execute)

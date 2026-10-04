from typing import Any

from easy_quant.application.services.strategy_quick_test import execute_strategy_tick
from easy_quant.worker.registry import JobHandlerRegistry


def register_strategy_handlers(registry: JobHandlerRegistry, container: Any) -> None:
    registry.register("strategy.validate", lambda job: {"validated": bool(job.payload)})
    registry.register(
        "strategy.run", lambda job: execute_strategy_tick(container, job.payload, job_id=job.id)
    )

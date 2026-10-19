from typing import Any

from easy_quant.application.services.strategy_quick_test import execute_strategy_tick
from easy_quant.domain.scheduling.entities import Job
from easy_quant.worker.registry import JobHandlerRegistry


def register_strategy_handlers(registry: JobHandlerRegistry, container: Any) -> None:
    registry.register("strategy.validate", lambda job: {"validated": bool(job.payload)})

    def quick_test(job: Job):
        try:
            return execute_strategy_tick(container, job.payload, job_id=job.id)
        finally:
            # 只为排队/租约恢复临时传递；最终成功与失败记录均不保留代码快照。
            job.payload.pop("source_code", None)

    registry.register("strategy.run", quick_test)

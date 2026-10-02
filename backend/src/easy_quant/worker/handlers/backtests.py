from typing import Any

from easy_quant.application.services.backtest_runtime import execute_backtest
from easy_quant.domain.scheduling.entities import Job
from easy_quant.worker.registry import JobHandlerRegistry


def register_backtest_handlers(registry: JobHandlerRegistry, container: Any) -> None:
    def execute(job: Job) -> dict[str, object]:
        run_id = str(job.payload["backtest_id"])
        container.backtests.mark_running(run_id)
        try:
            return execute_backtest(container, run_id)
        except Exception as error:
            container.backtests.mark_failed(run_id, str(error))
            raise

    registry.register("backtest.run", execute)

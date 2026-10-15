import logging
from typing import Any

from easy_quant.application.services.backtest_runtime import execute_backtest
from easy_quant.application.services.run_profile import RunProfile
from easy_quant.domain.scheduling.entities import Job
from easy_quant.domain.shared.errors import DomainError
from easy_quant.worker.registry import JobHandlerRegistry


def register_backtest_handlers(registry: JobHandlerRegistry, container: Any) -> None:
    def execute(job: Job) -> dict[str, object]:
        run_id = str(job.payload["backtest_id"])
        profile = RunProfile()
        try:
            container.backtests.mark_running(run_id)
            return execute_backtest(container, run_id, profile=profile)
        except Exception as error:
            message = (
                str(error)
                if isinstance(error, DomainError)
                else "回测执行失败，请检查 worker 日志或数据库连接"
            )
            if container.database_session is not None:
                try:
                    container.database_session.remove()
                except Exception:
                    logging.getLogger(__name__).exception("回测读连接清理失败 run_id=%s", run_id)
            try:
                container.backtests.update_status(
                    run_id,
                    {
                        "status": "failed",
                        "progress": 100,
                        "error": message,
                        "error_details": dict(error.details)
                        if isinstance(error, DomainError)
                        else {},
                        "timing": profile.snapshot(),
                        "execution": {"stage": "failed", "failed_stage": profile.stage},
                    },
                )
            except Exception:
                logging.getLogger(__name__).exception("回测失败状态保存失败 run_id=%s", run_id)
            raise

    registry.register("backtest.run", execute)

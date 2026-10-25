from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from easy_quant.application.ports.core import Clock, Sleeper
from easy_quant.application.ports.jobs import JobRepository
from easy_quant.domain.shared.errors import DomainError
from easy_quant.worker.registry import JobHandlerRegistry

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Worker:
    worker_id: str
    jobs: JobRepository
    handlers: JobHandlerRegistry
    clock: Clock
    sleeper: Sleeper
    lease_duration: timedelta = timedelta(minutes=5)
    poll_seconds: float = 1.0
    poll_hook: Callable[[], None] | None = None
    failure_hook: Callable[[], None] | None = None
    session_cleanup: Callable[[], None] | None = None

    def run_once(self) -> bool:
        try:
            self._release_session()
            if self.poll_hook is not None:
                self.poll_hook()
            # 调度读取可能建立 REPEATABLE READ 快照；不能带入独立领取后的任务。
            self._release_session()
            return self._run_job()
        finally:
            # 包括空队列、调度/领取/保存异常，不把事务留到睡眠或下一轮。
            self._release_session()

    def _release_session(self) -> None:
        if self.session_cleanup is not None:
            self.session_cleanup()

    def _run_job(self) -> bool:
        now = self.clock.now()
        job = self.jobs.claim_due(self.worker_id, now, now + self.lease_duration)
        if job is None:
            return False
        logger.info(
            "任务已领取 job_id=%s job_type=%s attempt=%s",
            job.id,
            job.job_type,
            job.attempt_count,
        )
        if job.job_type == "strategy.run" and job.attempt_count > 3:
            job.payload.pop("source_code", None)
            job.fail(
                self.worker_id,
                {
                    "code": "quick_test_retry_exhausted",
                    "message": "快速测试多次中断，已停止自动重试。请检查 worker 资源后重新发起。",
                },
            )
            self.jobs.save(job)
            return True
        try:
            summary = self.handlers.get(job.job_type)(job) or {}
            job.succeed(self.worker_id, dict(summary))
        except Exception as exc:
            if job.job_type in {"live-analysis", "live.analyze"}:
                logger.exception(
                    "实盘任务执行失败 job_id=%s live_instance_id=%s live_name=%r phase=%s",
                    job.id,
                    job.payload.get("instance_id"),
                    job.payload.get("live_name"),
                    job.payload.get("phase"),
                )
            else:
                logger.exception("任务执行失败", extra={"job_id": job.id, "job_type": job.job_type})
            if self.failure_hook is not None:
                self.failure_hook()
            error: dict[str, Any] = {"code": "job_failed", "message": str(exc)}
            if job.job_type in {"live-analysis", "live.analyze"}:
                error.update(
                    live_instance_id=job.payload.get("instance_id"),
                    live_name=job.payload.get("live_name"),
                )
            if isinstance(exc, DomainError):
                error["code"] = exc.code
                error["details"] = dict(exc.details)
            job.fail(self.worker_id, error)
        self.jobs.save(job)
        if job.status.value == "succeeded":
            logger.info("任务已完成 job_id=%s job_type=%s", job.id, job.job_type)
        return True

    def run_forever(self) -> None:
        logger.info("worker 已启动 worker_id=%s", self.worker_id)
        while True:
            try:
                handled = self.run_once()
            except Exception:
                logger.exception("worker 轮询失败 worker_id=%s", self.worker_id)
                self.sleeper.sleep(max(5.0, self.poll_seconds))
                continue
            if not handled:
                self.sleeper.sleep(self.poll_seconds)


class SystemSleeper:
    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


def main() -> None:
    from easy_quant.bootstrap import build_worker

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    build_worker().run_forever()


if __name__ == "__main__":
    main()

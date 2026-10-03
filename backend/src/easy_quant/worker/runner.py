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

    def run_once(self) -> bool:
        if self.poll_hook is not None:
            self.poll_hook()
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
        try:
            summary = self.handlers.get(job.job_type)(job) or {}
            job.succeed(self.worker_id, dict(summary))
        except Exception as exc:
            logger.exception("任务执行失败", extra={"job_id": job.id, "job_type": job.job_type})
            error: dict[str, Any] = {"code": "job_failed", "message": str(exc)}
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

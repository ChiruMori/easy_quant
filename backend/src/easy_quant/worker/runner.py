from __future__ import annotations

import logging
import time
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import Event, Thread
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from easy_quant.application.ports.core import Clock, Sleeper
from easy_quant.application.ports.jobs import JobContinuation, JobRepository
from easy_quant.application.ports.storage_errors import StorageFailure
from easy_quant.domain.shared.errors import DomainError
from easy_quant.infrastructure.data_sources.request_budget import (
    CollectionCancelled,
    RequestBudget,
    request_budget,
)
from easy_quant.infrastructure.persistence.recovery import log_database_error, storage_failure
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
    heartbeat_seconds: float = 30.0
    poll_hook: Callable[[], None] | None = None
    failure_hook: Callable[[], None] | None = None
    session_cleanup: Callable[[], None] | None = None

    _last_data_request: datetime | None = field(default=None, init=False)

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
            try:
                self.session_cleanup()
            except SQLAlchemyError as error:
                raise storage_failure(error, "job.release_read_session") from error

    def _run_job(self) -> bool:
        now = self.clock.now()
        job = self.jobs.claim_due(self.worker_id, now, now + self.lease_duration)
        if job is None:
            return False
        log = (
            logger.debug
            if job.job_type in {"market-data-nightly", "market-data-collection"}
            else logger.info
        )
        log(
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
            self.jobs.finish_claim(job, self.worker_id, self.clock.now())
            return True
        stop = Event()
        lost = Event()

        def heartbeat() -> None:
            interval = min(self.heartbeat_seconds, self.lease_duration.total_seconds() / 3)
            while not stop.wait(max(0.001, interval)):
                now = self.clock.now()
                try:
                    renewed = self.jobs.renew_lease(
                        job.id, self.worker_id, job.attempt_count, now, now + self.lease_duration
                    )
                except SQLAlchemyError as error:
                    log_database_error(logger, error, "job.heartbeat", job_id=job.id)
                    continue
                except Exception:
                    # Retry while the current lease remains valid; completion is still fenced.
                    logger.exception("任务续租失败 job_id=%s attempt=%s", job.id, job.attempt_count)
                    continue
                if not renewed:
                    lost.set()
                    logger.error("任务租约失效 job_id=%s attempt=%s", job.id, job.attempt_count)
                    return
                logger.debug("任务已续租 job_id=%s attempt=%s", job.id, job.attempt_count)

        heartbeat_thread = Thread(target=heartbeat, name="job-lease-heartbeat", daemon=True)
        heartbeat_thread.start()
        try:

            def check_collection():
                try:
                    current = self.jobs.is_claim_current(
                        job.id, self.worker_id, job.attempt_count, self.clock.now()
                    )
                except SQLAlchemyError as error:
                    raise storage_failure(error, "job.check_claim") from error
                if lost.is_set() or not current:
                    raise CollectionCancelled()

            data_job = job.job_type in {
                "market-data-nightly",
                "market-data-collection",
                "market-data-acquisition",
                "index-daily-update",
            }

            def check_wait():
                if lost.is_set():
                    raise CollectionCancelled()

            budget = RequestBudget(
                self.clock,
                self.sleeper,
                check_collection,
                last=self._last_data_request,
                release=self._release_session,
                check_wait=check_wait,
            )
            try:
                with request_budget(budget) if data_job else nullcontext():
                    summary = self.handlers.get(job.job_type)(job) or {}
            finally:
                if data_job:
                    self._last_data_request = budget.last
            job.error_summary = {}
            if isinstance(summary, JobContinuation):
                job.result_summary = summary.summary
                job.fail(self.worker_id, {}, retry_at=summary.resume_at)
            else:
                job.succeed(self.worker_id, dict(summary))
        except CollectionCancelled:
            lost.set()
            logger.info("采集已停止：任务删除、取消或租约失效 job_id=%s", job.id)
        except Exception as exc:
            database_error = isinstance(exc, (StorageFailure, SQLAlchemyError))
            if database_error:
                log_database_error(
                    logger,
                    exc,
                    "job.execute",
                    job_id=job.id,
                    dataset=job.payload.get("collection", {}).get(
                        "dataset_key", job.payload.get("dataset_key")
                    ),
                    report_period=job.payload.get("collection", {}).get("report_period"),
                    task_type=job.job_type,
                )
                if isinstance(exc, SQLAlchemyError):
                    exc = storage_failure(exc, "job.execute")
                job.result_summary.update(message="数据库故障，任务已终止")
            elif job.job_type in {"live-analysis", "live.analyze"}:
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
                try:
                    self.failure_hook()
                except SQLAlchemyError as cleanup_error:
                    log_database_error(logger, cleanup_error, "job.failure_cleanup", job_id=job.id)
            error: dict[str, Any] = {"code": "job_failed", "message": str(exc)}
            if job.job_type in {"live-analysis", "live.analyze"}:
                error.update(
                    live_instance_id=job.payload.get("instance_id"),
                    live_name=job.payload.get("live_name"),
                )
            if isinstance(exc, DomainError):
                error["code"] = exc.code
                error["details"] = dict(exc.details)
                if job.payload.get("collection") and not database_error:
                    job.result_summary = dict(exc.details)
            retry_at = None
            if (
                job.job_type in {"market-data-nightly", "market-data-acquisition"}
                and job.attempt_count < 3
                and not job.payload.get("collection")
                and not database_error
            ):
                retry_at = self.clock.now() + timedelta(minutes=5 * job.attempt_count)
                error["retry_at"] = retry_at.isoformat()
            if retry_at is not None:
                error["message"] = f"{error['message']}；已安排自动重试"
                logger.warning(
                    "任务等待自动重试 job_id=%s attempt=%s retry_at=%s",
                    job.id,
                    job.attempt_count,
                    retry_at.isoformat(),
                )
            job.fail(self.worker_id, error, retry_at=retry_at)
        finally:
            stop.set()
            heartbeat_thread.join(timeout=5)
        try:
            finished = (
                False
                if lost.is_set()
                else self.jobs.finish_claim(job, self.worker_id, self.clock.now())
            )
        except SQLAlchemyError as finish_error:
            log_database_error(
                logger, finish_error, "job.finish_claim", job_id=job.id, result_not_saved=True
            )
            raise storage_failure(finish_error, "job.finish_claim") from finish_error
        if lost.is_set() or not finished:
            logger.error("丢弃失效任务结果 job_id=%s attempt=%s", job.id, job.attempt_count)
            return True
        if job.status.value == "succeeded":
            logger.info("任务已完成 job_id=%s job_type=%s", job.id, job.job_type)
        return True

    def run_forever(self) -> None:
        logger.info("worker 已启动 worker_id=%s", self.worker_id)
        while True:
            try:
                handled = self.run_once()
            except (StorageFailure, SQLAlchemyError) as error:
                log_database_error(
                    logger, error, "worker.coordinator", status="无法领取或持久化任务，停止worker"
                )
                raise SystemExit(1) from None
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
    logging.getLogger("httpx").setLevel(logging.WARNING)
    build_worker().run_forever()


if __name__ == "__main__":
    main()

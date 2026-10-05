from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, cast

import pytest

from easy_quant.domain.scheduling.entities import Job, JobStatus
from easy_quant.worker.handlers.market_data import register_market_data_handlers
from easy_quant.worker.registry import JobHandlerRegistry
from easy_quant.worker.runner import Worker
from tests.fakes.core import FixedClock, VirtualSleeper
from tests.fakes.platform import make_test_container


class InMemoryJobs:
    def __init__(self, jobs: list[Job]) -> None:
        self.jobs = {job.id: job for job in jobs}

    def enqueue(self, job: Job) -> Job:
        existing = next(
            (item for item in self.jobs.values() if item.business_key == job.business_key), None
        )
        if existing is not None:
            return existing
        self.jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def claim_due(self, worker_id: str, now: datetime, lease_until: datetime) -> Job | None:
        for job in self.jobs.values():
            if job.can_be_claimed(now):
                job.claim(worker_id, now, lease_until)
                return job
        return None

    def save(self, job: Job) -> None:
        self.jobs[job.id] = job


def test_worker_runs_due_job(fixed_now: datetime, caplog) -> None:
    job = Job("job-1", "demo", "demo:1", {}, fixed_now)
    jobs = InMemoryJobs([job])
    handlers = JobHandlerRegistry()
    handlers.register("demo", lambda job: {"ok": bool(job.id)})
    worker = Worker("worker-1", jobs, handlers, FixedClock(fixed_now), VirtualSleeper())

    with caplog.at_level(logging.INFO, logger="easy_quant.worker.runner"):
        assert worker.run_once() is True
    assert job.status is JobStatus.SUCCEEDED
    assert job.result_summary == {"ok": True}
    assert "任务已领取 job_id=job-1" in caplog.text
    assert "任务已完成 job_id=job-1" in caplog.text


def test_expired_lease_is_recovered(fixed_now: datetime) -> None:
    job = Job(
        "job-1",
        "demo",
        "demo:1",
        {},
        fixed_now - timedelta(minutes=2),
        status=JobStatus.RUNNING,
        lease_owner="dead-worker",
        lease_until=fixed_now - timedelta(minutes=1),
    )
    jobs = InMemoryJobs([job])
    handlers = JobHandlerRegistry()
    handlers.register("demo", lambda job: {"recovered": bool(job.id)})
    worker = Worker("worker-2", jobs, handlers, FixedClock(fixed_now), VirtualSleeper())

    worker.run_once()

    assert job.status is JobStatus.SUCCEEDED
    assert job.attempt_count == 1


def test_enqueue_is_idempotent(fixed_now: datetime) -> None:
    first = Job("job-1", "demo", "same-key", {}, fixed_now)
    jobs = InMemoryJobs([first])

    result = jobs.enqueue(Job("job-2", "demo", "same-key", {}, fixed_now))

    assert result.id == "job-1"
    assert len(jobs.jobs) == 1


def test_worker_recovers_session_before_saving_failed_job(fixed_now: datetime) -> None:
    job = Job("job-1", "demo", "demo:1", {}, fixed_now)
    calls: list[str] = []

    class RecoveringJobs(InMemoryJobs):
        def save(self, job: Job) -> None:
            assert calls == ["rollback"]
            super().save(job)

    jobs = RecoveringJobs([job])
    handlers = JobHandlerRegistry()

    def fail(job: Job) -> dict[str, object]:
        del job
        raise RuntimeError("database failed")

    handlers.register("demo", fail)
    worker = Worker(
        "worker-1",
        jobs,
        handlers,
        FixedClock(fixed_now),
        VirtualSleeper(),
        failure_hook=lambda: calls.append("rollback"),
    )
    assert worker.run_once() is True
    assert job.status is JobStatus.FAILED


def test_acquisition_handler_rolls_back_before_recording_failure(fixed_now: datetime) -> None:
    container = make_test_container()
    container.state.acquisitions["task-1"] = {"id": "task-1", "status": "queued"}

    class FailedSession:
        recovered = False

        def rollback(self) -> None:
            self.recovered = True

    class FailedSync:
        def sync(self, *_args, **_kwargs):
            raise RuntimeError("cache write failed")

    session = FailedSession()
    container.database_session = session
    container.data_sync = cast(Any, FailedSync())
    registry = JobHandlerRegistry()
    register_market_data_handlers(registry, container)
    job = Job(
        "job-1",
        "market-data-acquisition",
        "task-1",
        {"task_id": "task-1", "dataset_key": "securities"},
        fixed_now,
    )
    with pytest.raises(RuntimeError, match="cache write failed"):
        registry.get("market-data-acquisition")(job)
    assert session.recovered
    assert container.state.acquisitions["task-1"]["status"] == "failed"

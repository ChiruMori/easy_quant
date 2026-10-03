from __future__ import annotations

import logging
from datetime import datetime, timedelta

from easy_quant.domain.scheduling.entities import Job, JobStatus
from easy_quant.worker.registry import JobHandlerRegistry
from easy_quant.worker.runner import Worker
from tests.fakes.core import FixedClock, VirtualSleeper


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

from datetime import timedelta
from threading import Event

from easy_quant.domain.scheduling.entities import Job, JobStatus
from easy_quant.infrastructure.persistence.repositories.jobs import InMemoryJobRepository
from easy_quant.worker.registry import JobHandlerRegistry
from easy_quant.worker.runner import Worker
from tests.fakes.core import FixedClock, VirtualSleeper


def test_long_handler_is_renewed_and_heartbeat_stops(fixed_now):
    renewed = Event()
    seen = []

    class Jobs(InMemoryJobRepository):
        def renew_lease(self, job_id, worker_id, attempt, now, lease_until):
            accepted = super().renew_lease(job_id, worker_id, attempt, now, lease_until)
            seen.append((attempt, accepted))
            renewed.set()
            return accepted

    jobs = Jobs()
    jobs.enqueue(Job("j", "demo", "b", {}, fixed_now))
    registry = JobHandlerRegistry()

    def handle(job) -> dict[str, object]:
        assert renewed.wait(2)
        return {"done": True}

    registry.register("demo", handle)
    worker = Worker(
        "w", jobs, registry, FixedClock(fixed_now), VirtualSleeper(), heartbeat_seconds=0.01
    )
    assert worker.run_once()
    assert seen and all(attempt == 1 and accepted for attempt, accepted in seen)
    saved = jobs.get("j")
    assert saved is not None and saved.status == JobStatus.SUCCEEDED
    # A terminal result cannot be renewed or reclaimed.
    assert not jobs.renew_lease("j", "w", 1, fixed_now, fixed_now + timedelta(minutes=5))
    assert jobs.claim_due("other", fixed_now, fixed_now + timedelta(minutes=5)) is None


def test_reclaimed_attempt_fences_old_result_even_for_same_worker_id(fixed_now):
    jobs = InMemoryJobRepository()
    jobs.enqueue(Job("j", "demo", "b", {}, fixed_now))
    first = jobs.claim_due("same", fixed_now, fixed_now + timedelta(seconds=1))
    assert first is not None
    later = fixed_now + timedelta(seconds=2)
    second = jobs.claim_due("same", later, later + timedelta(minutes=5))
    assert second is not None and second.attempt_count == 2
    first.succeed("same", {"stale": True})
    assert not jobs.finish_claim(first, "same", later)
    assert not jobs.renew_lease("j", "same", 1, later, later + timedelta(minutes=5))
    second.succeed("same", {"fresh": True})
    assert jobs.finish_claim(second, "same", later)
    saved = jobs.get("j")
    assert saved is not None and saved.result_summary == {"fresh": True}


def test_expired_lease_cannot_be_resurrected_or_completed(fixed_now):
    jobs = InMemoryJobRepository()
    jobs.enqueue(Job("j", "demo", "b", {}, fixed_now))
    job = jobs.claim_due("w", fixed_now, fixed_now + timedelta(seconds=1))
    assert job is not None
    extended = fixed_now + timedelta(minutes=5)
    assert jobs.renew_lease("j", "w", 1, fixed_now + timedelta(milliseconds=500), extended)
    # Beyond the original lease, the renewed handler must not be reclaimed.
    assert jobs.claim_due("other", fixed_now + timedelta(seconds=2), extended) is None
    later = extended
    assert not jobs.renew_lease("j", "w", 1, later, later + timedelta(minutes=5))
    job.succeed("w")
    assert not jobs.finish_claim(job, "w", later)


def test_worker_drops_result_after_losing_lease(fixed_now, caplog):
    lost = Event()

    class Jobs(InMemoryJobRepository):
        def renew_lease(self, job_id, worker_id, attempt, now, lease_until):
            lost.set()
            return False

    jobs = Jobs()
    jobs.enqueue(Job("j", "demo", "b", {}, fixed_now))
    registry = JobHandlerRegistry()

    def handle(job) -> dict[str, object]:
        assert lost.wait(2)
        return {"stale": True}

    registry.register("demo", handle)
    worker = Worker(
        "w", jobs, registry, FixedClock(fixed_now), VirtualSleeper(), heartbeat_seconds=0.01
    )
    assert worker.run_once()
    saved = jobs.get("j")
    assert saved is not None and saved.status == JobStatus.RUNNING
    assert not saved.result_summary
    assert "丢弃失效任务结果" in caplog.text

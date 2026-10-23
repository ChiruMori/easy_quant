import json
from datetime import datetime
from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy.orm import Session

from easy_quant.domain.scheduling.entities import Job, JobStatus
from easy_quant.domain.shared.errors import StateConflictError
from easy_quant.infrastructure.persistence.repositories.runtime import SqlAlchemyBacktestStore
from easy_quant.worker.registry import JobHandlerRegistry
from easy_quant.worker.runner import Worker
from tests.application.test_job_runner import InMemoryJobs
from tests.fakes.core import FixedClock, VirtualSleeper


@pytest.mark.parametrize("cleanup_enabled", [False, True])
def test_run_committed_during_schedule_poll_is_visible_after_independent_claim(
    fixed_now: datetime, cleanup_enabled: bool
):
    committed: dict[str, str] = {}

    class RepeatableReadScope:
        snapshot: dict[str, str] | None = None

        def get(self, _model, key):
            if self.snapshot is None:
                self.snapshot = dict(committed)
            payload = self.snapshot.get(key)
            return SimpleNamespace(payload_json=payload, name=None) if payload is not None else None

        def remove(self):
            self.snapshot = None

    scope = RepeatableReadScope()
    store = SqlAlchemyBacktestStore(cast(Session, scope))
    jobs = InMemoryJobs([])
    handlers = JobHandlerRegistry()
    submitted: list[Job] = []

    def poll():
        run_id = f"run-{len(submitted)}"
        assert store.get(run_id) is None  # 调度阶段已建立早于 API 提交的快照。
        committed[run_id] = json.dumps({"id": run_id, "status": "queued"})
        job = Job(f"job-{run_id}", "backtest.run", run_id, {"backtest_id": run_id}, fixed_now)
        jobs.enqueue(job)  # API 在独立事务同时提交记录和任务。
        submitted.append(job)

    def execute(job):
        run = store.get(job.payload["backtest_id"])
        if run is None:
            raise StateConflictError("回测记录不存在")
        return {"run_id": run["id"]}

    handlers.register("backtest.run", execute)
    worker = Worker(
        "w",
        jobs,
        handlers,
        FixedClock(fixed_now),
        VirtualSleeper(),
        poll_hook=poll,
        session_cleanup=scope.remove if cleanup_enabled else None,
    )
    for _ in range(2):
        assert worker.run_once()
    expected = JobStatus.SUCCEEDED if cleanup_enabled else JobStatus.FAILED
    assert all(job.status is expected for job in submitted)
    if cleanup_enabled:
        assert scope.snapshot is None
        assert [job.result_summary["run_id"] for job in submitted] == ["run-0", "run-1"]
    else:
        # 未配置边界时，fake 确实重现现网日志，而不是自动返回最新行。
        assert all(job.error_summary["message"] == "回测记录不存在" for job in submitted)


@pytest.mark.parametrize("outcome", ["idle", "success", "handler", "poll", "claim", "save"])
def test_worker_closes_shared_session_on_all_exit_paths(fixed_now, outcome):
    state = {"active": True, "resets": 0, "handled": False}
    job = Job("j", "demo", "b", {}, fixed_now)

    def cleanup():
        state["active"] = False
        state["resets"] += 1

    def poll():
        assert not state["active"]
        state["active"] = True
        if outcome == "poll":
            raise RuntimeError("poll failed")

    class Jobs(InMemoryJobs):
        def claim_due(self, worker_id, now, lease_until):
            assert not state["active"]  # 调度快照在领取/处理之前结束。
            if outcome == "claim":
                state["active"] = True
                raise RuntimeError("claim failed")
            return super().claim_due(worker_id, now, lease_until)

        def save(self, job):
            if outcome == "save":
                raise RuntimeError("save failed")
            return super().save(job)

    def handle(job: Job) -> dict[str, object]:
        assert not state["active"]
        state["active"] = state["handled"] = True
        if outcome == "handler":
            raise RuntimeError("handler failed")
        return {"ok": True}

    jobs = Jobs([] if outcome == "idle" else [job])
    handlers = JobHandlerRegistry()
    handlers.register("demo", handle)
    worker = Worker(
        "w",
        jobs,
        handlers,
        FixedClock(fixed_now),
        VirtualSleeper(),
        poll_hook=poll,
        session_cleanup=cleanup,
    )
    if outcome in {"poll", "claim", "save"}:
        with pytest.raises(RuntimeError, match=f"{outcome} failed"):
            worker.run_once()
    else:
        assert worker.run_once() is (outcome != "idle")
    assert not state["active"]
    assert state["resets"] >= 2
    if outcome == "handler":
        assert job.status is JobStatus.FAILED

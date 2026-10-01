from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from easy_quant.domain.shared.errors import StateConflictError
from easy_quant.domain.shared.value_objects import ensure_utc


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class Job:
    id: str
    job_type: str
    business_key: str
    payload: dict[str, Any]
    available_at: datetime
    status: JobStatus = JobStatus.QUEUED
    attempt_count: int = 0
    lease_owner: str | None = None
    lease_until: datetime | None = None
    result_summary: dict[str, Any] = field(default_factory=dict)
    error_summary: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.available_at = ensure_utc(self.available_at)
        if self.lease_until is not None:
            self.lease_until = ensure_utc(self.lease_until)

    def can_be_claimed(self, now: datetime) -> bool:
        now = ensure_utc(now)
        if self.status is JobStatus.QUEUED:
            return self.available_at <= now
        return (
            self.status is JobStatus.RUNNING
            and self.lease_until is not None
            and self.lease_until <= now
        )

    def claim(self, worker_id: str, now: datetime, lease_until: datetime) -> None:
        if not self.can_be_claimed(now):
            raise StateConflictError("任务当前不可领取")
        self.status = JobStatus.RUNNING
        self.lease_owner = worker_id
        self.lease_until = ensure_utc(lease_until)
        self.attempt_count += 1

    def renew(self, worker_id: str, lease_until: datetime) -> None:
        self._ensure_lease_owner(worker_id)
        self.lease_until = ensure_utc(lease_until)

    def succeed(self, worker_id: str, summary: dict[str, Any] | None = None) -> None:
        self._ensure_lease_owner(worker_id)
        self.status = JobStatus.SUCCEEDED
        self.result_summary = summary or {}
        self.lease_owner = None
        self.lease_until = None

    def fail(
        self,
        worker_id: str,
        error: dict[str, Any],
        retry_at: datetime | None = None,
    ) -> None:
        self._ensure_lease_owner(worker_id)
        self.error_summary = error
        self.lease_owner = None
        self.lease_until = None
        if retry_at is None:
            self.status = JobStatus.FAILED
        else:
            self.status = JobStatus.QUEUED
            self.available_at = ensure_utc(retry_at)

    def _ensure_lease_owner(self, worker_id: str) -> None:
        if self.status is not JobStatus.RUNNING or self.lease_owner != worker_id:
            raise StateConflictError("只有当前租约持有者可以更新任务")


class ScheduleKind(StrEnum):
    CRON = "cron"
    INTERVAL = "interval"


@dataclass(slots=True)
class ScheduledTask:
    id: str
    task_type: str
    schedule_kind: ScheduleKind
    schedule_expression: str
    timezone: str
    configuration: dict[str, Any]
    next_run_at: datetime
    enabled: bool = True

    def __post_init__(self) -> None:
        self.next_run_at = ensure_utc(self.next_run_at)

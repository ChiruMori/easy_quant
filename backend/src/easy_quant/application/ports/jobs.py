from __future__ import annotations

from datetime import datetime
from typing import Protocol

from easy_quant.domain.scheduling.entities import Job


class JobRepository(Protocol):
    def enqueue(self, job: Job) -> Job: ...

    def get(self, job_id: str) -> Job | None: ...

    def claim_due(self, worker_id: str, now: datetime, lease_until: datetime) -> Job | None: ...

    def save(self, job: Job) -> None: ...


class JobHandler(Protocol):
    def __call__(self, job: Job) -> dict[str, object] | None: ...

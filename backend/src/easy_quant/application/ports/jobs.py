from __future__ import annotations

from datetime import datetime
from typing import Protocol

from easy_quant.domain.scheduling.entities import Job


class JobRepository(Protocol):
    def enqueue(self, job: Job) -> Job: ...

    def get(self, job_id: str) -> Job | None: ...

    def claim_due(self, worker_id: str, now: datetime, lease_until: datetime) -> Job | None: ...

    def save(self, job: Job) -> None: ...

    def renew_lease(
        self, job_id: str, worker_id: str, attempt: int, now: datetime, lease_until: datetime
    ) -> bool: ...

    def finish_claim(self, job: Job, worker_id: str, now: datetime) -> bool: ...


class JobPageQuery(Protocol):
    def list_page(self, page: int, page_size: int) -> tuple[list[Job], int, int]: ...


class JobHandler(Protocol):
    def __call__(self, job: Job) -> dict[str, object] | None: ...

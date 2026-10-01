from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from easy_quant.domain.scheduling.entities import Job, JobStatus
from easy_quant.infrastructure.persistence.models.scheduling import JobModel


class InMemoryJobRepository:
    def __init__(self) -> None:
        self.items: dict[str, Job] = {}

    def enqueue(self, job: Job) -> Job:
        existing = next(
            (item for item in self.items.values() if item.business_key == job.business_key), None
        )
        if existing:
            return existing
        self.items[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        return self.items.get(job_id)

    def claim_due(self, worker_id: str, now: datetime, lease_until: datetime) -> Job | None:
        job = next((item for item in self.items.values() if item.can_be_claimed(now)), None)
        if job:
            job.claim(worker_id, now, lease_until)
        return job

    def save(self, job: Job) -> None:
        self.items[job.id] = job

    def list_all(self) -> list[Job]:
        return list(self.items.values())


class SqlAlchemyJobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def enqueue(self, job: Job) -> Job:
        existing = self.session.scalar(
            select(JobModel).where(JobModel.business_key == job.business_key)
        )
        if existing:
            return self._to_domain(existing)
        self.session.add(self._to_model(job))
        self.session.commit()
        return job

    def get(self, job_id: str) -> Job | None:
        row = self.session.get(JobModel, job_id)
        return self._to_domain(row) if row else None

    def claim_due(self, worker_id: str, now: datetime, lease_until: datetime) -> Job | None:
        row = self.session.scalar(
            select(JobModel)
            .where(
                JobModel.available_at <= now,
                or_(
                    JobModel.status == JobStatus.QUEUED.value,
                    (JobModel.status == JobStatus.RUNNING.value) & (JobModel.lease_until <= now),
                ),
            )
            .order_by(JobModel.available_at)
            .with_for_update(skip_locked=True)
        )
        if row is None:
            return None
        job = self._to_domain(row)
        job.claim(worker_id, now, lease_until)
        self._copy(job, row)
        self.session.commit()
        return job

    def save(self, job: Job) -> None:
        row = self.session.get(JobModel, job.id)
        if row is None:
            self.session.add(self._to_model(job))
        else:
            self._copy(job, row)
        self.session.commit()

    def list_all(self) -> list[Job]:
        return [self._to_domain(row) for row in self.session.scalars(select(JobModel))]

    @staticmethod
    def _to_domain(row: JobModel) -> Job:
        return Job(
            row.id,
            row.job_type,
            row.business_key,
            json.loads(row.payload_json),
            row.available_at,
            JobStatus(row.status),
            row.attempt_count,
            row.lease_owner,
            row.lease_until,
            json.loads(row.result_json),
            json.loads(row.error_json),
        )

    @staticmethod
    def _to_model(job: Job) -> JobModel:
        return JobModel(
            id=job.id,
            job_type=job.job_type,
            business_key=job.business_key,
            status=job.status.value,
            payload_json=json.dumps(job.payload, ensure_ascii=False, default=str),
            available_at=job.available_at,
            lease_owner=job.lease_owner,
            lease_until=job.lease_until,
            attempt_count=job.attempt_count,
            result_json=json.dumps(job.result_summary, ensure_ascii=False, default=str),
            error_json=json.dumps(job.error_summary, ensure_ascii=False, default=str),
        )

    @staticmethod
    def _copy(job: Job, row: JobModel) -> None:
        row.status = job.status.value
        row.payload_json = json.dumps(job.payload, ensure_ascii=False, default=str)
        row.available_at = job.available_at
        row.lease_owner = job.lease_owner
        row.lease_until = job.lease_until
        row.attempt_count = job.attempt_count
        row.result_json = json.dumps(job.result_summary, ensure_ascii=False, default=str)
        row.error_json = json.dumps(job.error_summary, ensure_ascii=False, default=str)

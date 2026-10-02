from datetime import datetime

from sqlalchemy import Boolean, Index, Integer, String, Text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from easy_quant.infrastructure.persistence.base import Base, UtcDateTime


class JobModel(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_claim", "status", "available_at", "lease_until"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    business_key: Mapped[str] = mapped_column(String(180), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    available_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False, index=True)
    lease_owner: Mapped[str | None] = mapped_column(String(80))
    lease_until: Mapped[datetime | None] = mapped_column(UtcDateTime(), index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_json: Mapped[str] = mapped_column(
        Text().with_variant(LONGTEXT(), "mysql"), nullable=False, default="{}"
    )
    error_json: Mapped[str] = mapped_column(
        Text().with_variant(LONGTEXT(), "mysql"), nullable=False, default="{}"
    )


class ScheduledTaskModel(Base):
    __tablename__ = "scheduled_tasks"
    __table_args__ = (Index("ix_scheduled_tasks_due", "enabled", "next_run_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_type: Mapped[str] = mapped_column(String(80), nullable=False)
    schedule_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    schedule_expression: Mapped[str] = mapped_column(String(100), nullable=False)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False)
    configuration_json: Mapped[str] = mapped_column(Text, nullable=False)
    next_run_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

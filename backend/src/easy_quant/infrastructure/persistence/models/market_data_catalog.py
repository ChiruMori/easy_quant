from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, LargeBinary, String
from sqlalchemy.dialects.mysql import LONGBLOB
from sqlalchemy.orm import Mapped, mapped_column

from easy_quant.infrastructure.persistence.base import Base, UtcDateTime


class DatasetModel(Base):
    __tablename__ = "datasets"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(30), nullable=False)


class DataSourceModel(Base):
    __tablename__ = "data_sources"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class SourceBindingModel(Base):
    __tablename__ = "source_bindings"
    dataset_key: Mapped[str] = mapped_column(ForeignKey("datasets.key"), primary_key=True)
    source_key: Mapped[str] = mapped_column(ForeignKey("data_sources.key"), primary_key=True)


class RawCacheModel(Base):
    __tablename__ = "raw_cache"
    request_identity: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_key: Mapped[str] = mapped_column(String(80), nullable=False)
    payload_gzip: Mapped[bytes] = mapped_column(
        LargeBinary().with_variant(LONGBLOB(), "mysql").with_variant(LONGBLOB(), "mariadb"),
        nullable=False,
    )
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)


class AcquisitionRunModel(Base):
    __tablename__ = "acquisition_runs"
    __table_args__ = (Index("ix_acquisition_request", "request_identity", "started_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_key: Mapped[str] = mapped_column(ForeignKey("datasets.key"), nullable=False)
    request_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    started_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(UtcDateTime())


class SourceAttemptModel(Base):
    __tablename__ = "source_attempts"
    run_id: Mapped[str] = mapped_column(ForeignKey("acquisition_runs.id"), primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_key: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    message: Mapped[str | None] = mapped_column(String(1000))

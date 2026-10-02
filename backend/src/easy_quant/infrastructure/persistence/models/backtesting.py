from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from easy_quant.infrastructure.persistence.base import Base, UtcDateTime


class DataSnapshotModel(Base):
    __tablename__ = "data_snapshots"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    content_sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)


class DataSnapshotChunkModel(Base):
    __tablename__ = "data_snapshot_chunks"
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("data_snapshots.id"), primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload: Mapped[bytes] = mapped_column(nullable=False)


class BacktestRunModel(Base):
    __tablename__ = "backtest_runs"
    __table_args__ = (Index("ix_backtests_owner_created", "owner_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    strategy_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("data_snapshots.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    progress: Mapped[int] = mapped_column(Integer, nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[str] = mapped_column(
        Text().with_variant(LONGTEXT(), "mysql"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)


class BacktestPeriodModel(Base):
    __tablename__ = "backtest_periods"
    run_id: Mapped[str] = mapped_column(ForeignKey("backtest_runs.id"), primary_key=True)
    trading_day: Mapped[date] = mapped_column(Date, primary_key=True)
    equity: Mapped[Decimal] = mapped_column(Numeric(28, 8), nullable=False)
    cash: Mapped[Decimal] = mapped_column(Numeric(28, 8), nullable=False)


class SimulatedTradeModel(Base):
    __tablename__ = "simulated_trades"
    __table_args__ = (UniqueConstraint("run_id", "sequence"),)
    run_id: Mapped[str] = mapped_column(ForeignKey("backtest_runs.id"), primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)


class BacktestMetricModel(Base):
    __tablename__ = "backtest_metrics"
    run_id: Mapped[str] = mapped_column(ForeignKey("backtest_runs.id"), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[Decimal | None] = mapped_column(Numeric(28, 12))

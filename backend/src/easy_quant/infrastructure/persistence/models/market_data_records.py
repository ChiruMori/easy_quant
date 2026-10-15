from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Column, Computed, Date, Index, Numeric, String, Table, UniqueConstraint
from sqlalchemy.dialects.mysql import INTEGER, VARBINARY
from sqlalchemy.orm import Mapped, mapped_column

from easy_quant.infrastructure.persistence.base import Base, UtcDateTime

provenance = Table(
    "bar_provenance",
    Base.metadata,
    Column("id", INTEGER(unsigned=True), primary_key=True, autoincrement=True),
    Column("source", String(40, collation="utf8mb4_bin"), nullable=False),
    Column("adjustment", String(20, collation="utf8mb4_bin"), nullable=False),
    Column("archive_sha256", String(64, collation="utf8mb4_bin")),
    Column(
        "archive_key",
        VARBINARY(256),
        Computed("CAST(IFNULL(archive_sha256, '') AS BINARY)", persisted=True),
    ),
    Column(
        "archive_is_null",
        INTEGER(unsigned=True),
        Computed("archive_sha256 IS NULL", persisted=True),
    ),
    Column("source_key", VARBINARY(160), Computed("CAST(source AS BINARY)", persisted=True)),
    Column("adjustment_key", VARBINARY(80), Computed("CAST(adjustment AS BINARY)", persisted=True)),
    UniqueConstraint(
        "source_key", "adjustment_key", "archive_key", "archive_is_null", name="uq_bar_provenance"
    ),
    mysql_charset="utf8mb4",
    mysql_engine="InnoDB",
)


class DailyBarModel(Base):
    __tablename__ = "daily_bars"
    __table_args__ = (
        Index("ix_daily_bars_coverage", "symbol", "trading_day"),
        Index("ix_daily_bars_day_symbol", "trading_day", "symbol"),
    )
    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    trading_day: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    high: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    low: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    close: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    volume: Mapped[Decimal] = mapped_column(Numeric(28, 4))
    available_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(28, 4))
    provenance_id: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False)


class HistoryImportStockModel(Base):
    __tablename__ = "history_import_stocks"
    archive_sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    row_count: Mapped[int]
    first_day: Mapped[date] = mapped_column(Date)
    last_day: Mapped[date] = mapped_column(Date)
    completed_at: Mapped[datetime] = mapped_column(UtcDateTime())


class TdxDailyCheckpointModel(Base):
    __tablename__ = "tdx_daily_checkpoints"
    trading_day: Mapped[date] = mapped_column(Date, primary_key=True)
    status: Mapped[str] = mapped_column(String(20))
    archive_sha256: Mapped[str | None] = mapped_column(String(64))
    row_count: Mapped[int] = mapped_column(default=0)
    checked_at: Mapped[datetime] = mapped_column(UtcDateTime())
    reason: Mapped[str] = mapped_column(String(200), default="")


class InstrumentModel(Base):
    __tablename__ = "instruments"
    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    exchange: Mapped[str] = mapped_column(String(40), nullable=False)
    listed_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")


class TradingDayModel(Base):
    __tablename__ = "trading_days"
    trading_day: Mapped[date] = mapped_column(Date, primary_key=True)


class JsonMarketRecordModel(Base):
    __tablename__ = "market_records"
    dataset_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    record_key: Mapped[str] = mapped_column(String(180), primary_key=True)
    payload_json: Mapped[str] = mapped_column(String(8000), nullable=False)
    available_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)

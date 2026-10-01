from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from easy_quant.infrastructure.persistence.base import Base, UtcDateTime


class DailyBarModel(Base):
    __tablename__ = "daily_bars"
    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    trading_day: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    high: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    low: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    close: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    volume: Mapped[Decimal] = mapped_column(Numeric(28, 4))
    available_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)


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

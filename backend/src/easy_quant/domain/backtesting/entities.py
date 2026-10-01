from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum


class BacktestStatus(StrEnum):
    PENDING = "pending"
    SNAPSHOTTING = "snapshotting"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    strategy_version_id: str
    symbols: tuple[str, ...]
    start_day: date
    end_day: date
    initial_cash: Decimal
    fee_rate: Decimal = Decimal("0.0003")
    slippage_rate: Decimal = Decimal("0.0001")
    benchmark: str | None = None
    random_seed: int = 0


@dataclass(frozen=True, slots=True)
class BacktestPeriod:
    trading_day: date
    equity: Decimal
    cash: Decimal
    positions_value: Decimal


@dataclass(frozen=True, slots=True)
class SimulatedTrade:
    trading_day: date
    symbol: str
    action: str
    quantity: Decimal
    price: Decimal
    fee: Decimal
    slippage: Decimal


@dataclass(slots=True)
class Portfolio:
    cash: Decimal
    positions: dict[str, Decimal] = field(default_factory=dict)

    def position(self, symbol: str) -> Decimal:
        return self.positions.get(symbol, Decimal(0))


@dataclass(slots=True)
class BacktestRun:
    id: str
    owner_id: str
    config: BacktestConfig
    snapshot_id: str
    application_version: str
    status: BacktestStatus = BacktestStatus.PENDING
    progress: int = 0
    periods: list[BacktestPeriod] = field(default_factory=list)
    trades: list[SimulatedTrade] = field(default_factory=list)
    metrics: dict[str, Decimal | int | None] = field(default_factory=dict)
    created_at: datetime | None = None
    error: str | None = None

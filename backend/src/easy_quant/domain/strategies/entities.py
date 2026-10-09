from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class StrategyRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


@dataclass(slots=True)
class StrategyDefinition:
    id: str
    owner_id: str
    name: str
    description: str = ""
    current_version_id: str | None = None


@dataclass(frozen=True, slots=True)
class StrategyVersion:
    id: str
    strategy_id: str
    number: int
    source_code: str
    content_sha256: str
    created_at: datetime
    parent_version_id: str | None = None


@dataclass(frozen=True, slots=True)
class Signal:
    symbol: str
    action: str
    quantity: Decimal
    reason: str
    trigger_price: Decimal | None = None
    trigger_operator: str | None = None
    ratio: Decimal | None = None
    ratio_basis: Decimal | None = None
    reference_price: Decimal | None = None


@dataclass(slots=True)
class StrategyRun:
    id: str
    version_id: str
    status: StrategyRunStatus
    parameters: dict[str, object]
    signals: list[Signal] = field(default_factory=list)
    stdout: str = ""
    error: str | None = None
    state: dict[str, object] = field(default_factory=dict)
    mock_usage: list[dict[str, object]] = field(default_factory=list)

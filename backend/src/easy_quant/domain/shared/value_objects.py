from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Self
from uuid import UUID, uuid4

MONEY_QUANTUM = Decimal("0.01")
PRICE_QUANTUM = Decimal("0.0001")
RATE_QUANTUM = Decimal("0.00000001")


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("时间必须包含时区")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class EntityId:
    value: UUID

    @classmethod
    def new(cls) -> Self:
        return cls(uuid4())

    @classmethod
    def parse(cls, value: str | UUID) -> Self:
        return cls(value if isinstance(value, UUID) else UUID(value))

    def __str__(self) -> str:
        return str(self.value)


def _decimal(value: Decimal | str | int, quantum: Decimal) -> Decimal:
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("数值格式无效") from exc
    if not parsed.is_finite():
        raise ValueError("数值必须是有限值")
    return parsed.quantize(quantum, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class Money:
    value: Decimal

    def __init__(self, value: Decimal | str | int) -> None:
        object.__setattr__(self, "value", _decimal(value, MONEY_QUANTUM))


@dataclass(frozen=True, slots=True)
class Price:
    value: Decimal

    def __init__(self, value: Decimal | str | int) -> None:
        parsed = _decimal(value, PRICE_QUANTUM)
        if parsed < 0:
            raise ValueError("价格不能为负数")
        object.__setattr__(self, "value", parsed)


@dataclass(frozen=True, slots=True)
class Quantity:
    value: Decimal

    def __init__(self, value: Decimal | str | int) -> None:
        parsed = _decimal(value, PRICE_QUANTUM)
        if parsed < 0:
            raise ValueError("数量不能为负数")
        object.__setattr__(self, "value", parsed)


@dataclass(frozen=True, slots=True)
class Rate:
    value: Decimal

    def __init__(self, value: Decimal | str | int) -> None:
        object.__setattr__(self, "value", _decimal(value, RATE_QUANTUM))


@dataclass(frozen=True, slots=True)
class TradingDay:
    value: date


@dataclass(frozen=True, slots=True)
class UtcTimestamp:
    value: datetime

    def __init__(self, value: datetime) -> None:
        object.__setattr__(self, "value", ensure_utc(value))

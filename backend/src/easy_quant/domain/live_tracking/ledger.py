from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from easy_quant.domain.shared.errors import StateConflictError


class OperationKind(StrEnum):
    CONFIRM = "confirm"
    REJECT = "reject"
    CORRECT = "correct"


@dataclass(frozen=True, slots=True)
class ActualOperation:
    id: str
    recommendation_id: str
    owner_id: str
    kind: OperationKind
    idempotency_key: str
    occurred_at: datetime
    symbol: str | None = None
    action: str | None = None
    quantity: Decimal = Decimal(0)
    price: Decimal = Decimal(0)
    fee: Decimal = Decimal(0)


@dataclass(frozen=True, slots=True)
class PortfolioLedgerEntry:
    id: str
    live_instance_id: str
    operation_id: str
    occurred_at: datetime
    cash_delta: Decimal
    symbol: str | None = None
    quantity_delta: Decimal = Decimal(0)
    price: Decimal = Decimal(0)


@dataclass(slots=True)
class ActualPortfolio:
    cash: Decimal
    positions: dict[str, Decimal] = field(default_factory=dict)
    costs: dict[str, Decimal] = field(default_factory=dict)


def entry_for_operation(
    entry_id: str, live_instance_id: str, operation: ActualOperation
) -> PortfolioLedgerEntry | None:
    if operation.kind is OperationKind.REJECT:
        return None
    if (
        not operation.symbol
        or operation.action not in {"buy", "sell"}
        or operation.quantity <= 0
        or operation.price <= 0
    ):
        raise StateConflictError("实际成交字段无效")
    direction = Decimal(1) if operation.action == "buy" else Decimal(-1)
    cash_delta = (
        -(operation.price * operation.quantity + operation.fee)
        if direction > 0
        else operation.price * operation.quantity - operation.fee
    )
    return PortfolioLedgerEntry(
        entry_id,
        live_instance_id,
        operation.id,
        operation.occurred_at,
        cash_delta,
        operation.symbol,
        direction * operation.quantity,
        operation.price,
    )


def rebuild_portfolio(
    initial_cash: Decimal, entries: list[PortfolioLedgerEntry]
) -> ActualPortfolio:
    portfolio = ActualPortfolio(initial_cash)
    for entry in sorted(entries, key=lambda item: (item.occurred_at, item.id)):
        next_cash = portfolio.cash + entry.cash_delta
        if next_cash < 0:
            raise StateConflictError("账本产生负现金")
        portfolio.cash = next_cash
        if entry.symbol:
            previous = portfolio.positions.get(entry.symbol, Decimal(0))
            current = previous + entry.quantity_delta
            if current < 0:
                raise StateConflictError("账本产生负持仓")
            if entry.quantity_delta > 0:
                previous_cost = portfolio.costs.get(entry.symbol, Decimal(0)) * previous
                portfolio.costs[entry.symbol] = (
                    previous_cost + entry.price * entry.quantity_delta
                ) / current
            if current == 0:
                portfolio.costs.pop(entry.symbol, None)
            portfolio.positions[entry.symbol] = current
    return portfolio

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from easy_quant.domain.live_tracking.ledger import ActualPortfolio
from easy_quant.domain.shared.errors import StateConflictError


@dataclass
class Reservations:
    cash: Decimal = Decimal(0)
    positions: dict[str, Decimal] = field(default_factory=dict)
    buy_symbols: set[str] = field(default_factory=set)


def reservations(items: Iterable[Mapping[str, Any]], exclude: str | None = None) -> Reservations:
    result = Reservations()
    for item in items:
        if item.get("status") != "pending" or item.get("id") == exclude:
            continue
        symbol = str(item["instrument_id"])
        quantity = Decimal(str(item["quantity"]))
        if item["action"] == "buy":
            result.buy_symbols.add(symbol)
            price = Decimal(str(item.get("suggested_price") or "0"))
            result.cash += Decimal(str(item.get("reserved_cash", quantity * price)))
        elif item["action"] == "sell":
            result.positions[symbol] = result.positions.get(symbol, Decimal(0)) + quantity
    return result


def ensure_available(portfolio: ActualPortfolio, locked: Reservations) -> None:
    if portfolio.cash < locked.cash:
        raise StateConflictError("可用资金不足，不能占用其他待处理建议的锁定资金")
    if any(
        portfolio.positions.get(key, Decimal(0)) < value for key, value in locked.positions.items()
    ):
        raise StateConflictError("可用持仓不足，不能占用其他待处理建议的锁定持仓")


def validate_lot(quantity: Decimal) -> None:
    if not quantity.is_finite() or quantity <= 0 or quantity % 100 != 0:
        raise StateConflictError("成交数量必须为正整百股")

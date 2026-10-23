from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal

from easy_quant.domain.backtesting.entities import SimulatedTrade


@dataclass(frozen=True, slots=True)
class SymbolPerformance:
    symbol: str
    quantity: Decimal
    remaining_cost: Decimal
    realized_profit: Decimal
    unrealized_profit: Decimal | None
    profit: Decimal | None
    market_value: Decimal | None


def attribute_trades(
    trades: Iterable[SimulatedTrade], prices: Mapping[str, Decimal]
) -> list[SymbolPerformance]:
    # 输入保持成交顺序：同一天不同阶段的成交不能重新按方向排序。
    totals: dict[str, tuple[Decimal, Decimal, Decimal]] = {}
    for trade in trades:
        quantity, cost, realized = totals.get(trade.symbol, (Decimal(0),) * 3)
        gross = trade.quantity * trade.price
        if trade.action == "buy":
            quantity += trade.quantity
            cost += gross + trade.fee
        elif trade.action == "sell":
            if trade.quantity > quantity or quantity <= 0:
                raise ValueError("成交明细中的卖出数量超过持仓")
            removed_cost = cost * trade.quantity / quantity
            realized += gross - trade.fee - removed_cost
            quantity -= trade.quantity
            cost = cost - removed_cost if quantity else Decimal(0)
        totals[trade.symbol] = quantity, cost, realized
    result = []
    for symbol, (quantity, cost, realized) in totals.items():
        price = prices.get(symbol)
        market_value = (
            Decimal(0) if not quantity else quantity * price if price is not None else None
        )
        unrealized = market_value - cost if market_value is not None else None
        result.append(
            SymbolPerformance(
                symbol,
                quantity,
                cost,
                realized,
                unrealized,
                realized + unrealized if unrealized is not None else None,
                market_value,
            )
        )
    return sorted(
        result, key=lambda row: (row.profit is None, -(row.profit or Decimal(0)), row.symbol)
    )

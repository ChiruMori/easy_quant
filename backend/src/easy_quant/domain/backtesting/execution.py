from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from easy_quant.domain.backtesting.entities import Portfolio, SimulatedTrade
from easy_quant.domain.strategies.entities import Signal

CENT = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class MarketBar:
    trading_day: date
    symbol: str
    close: Decimal
    tradable: bool = True
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None


def execute_signal(
    portfolio: Portfolio,
    signal: Signal,
    bar: MarketBar,
    fee_rate: Decimal,
    slippage_rate: Decimal,
    reference_price: Decimal | None = None,
) -> SimulatedTrade | None:
    if not bar.tradable or signal.action not in {"buy", "sell"} or signal.quantity <= 0:
        return None
    direction = Decimal(1) if signal.action == "buy" else Decimal(-1)
    base_price = reference_price if reference_price is not None else bar.close
    slippage = (base_price * slippage_rate).quantize(CENT, rounding=ROUND_HALF_UP)
    price = (base_price + direction * slippage).quantize(CENT, rounding=ROUND_HALF_UP)
    gross = price * signal.quantity
    fee = (gross * fee_rate).quantize(CENT, rounding=ROUND_HALF_UP)
    if signal.action == "buy":
        if portfolio.cash < gross + fee:
            return None
        portfolio.cash -= gross + fee
        previous = portfolio.position(signal.symbol)
        portfolio.costs[signal.symbol] = (
            portfolio.costs.get(signal.symbol, Decimal(0)) * previous + gross + fee
        ) / (previous + signal.quantity)
        portfolio.positions[signal.symbol] = portfolio.position(signal.symbol) + signal.quantity
    else:
        if portfolio.position(signal.symbol) < signal.quantity:
            return None
        portfolio.cash += gross - fee
        portfolio.positions[signal.symbol] = portfolio.position(signal.symbol) - signal.quantity
        if portfolio.positions[signal.symbol] == 0:
            portfolio.costs.pop(signal.symbol, None)
    return SimulatedTrade(
        bar.trading_day, signal.symbol, signal.action, signal.quantity, price, fee, slippage
    )

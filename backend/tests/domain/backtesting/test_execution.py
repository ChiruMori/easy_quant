from datetime import date
from decimal import Decimal

from easy_quant.domain.backtesting.entities import Portfolio
from easy_quant.domain.backtesting.execution import MarketBar, execute_signal
from easy_quant.domain.strategies.entities import Signal


def test_buy_sell_cash_positions_fees_and_slippage() -> None:
    portfolio = Portfolio(Decimal("1000"))
    bar = MarketBar(date(2026, 1, 1), "000001", Decimal("10"))
    buy = execute_signal(
        portfolio,
        Signal("000001", "buy", Decimal(10), "test"),
        bar,
        Decimal("0.001"),
        Decimal("0.01"),
    )
    assert buy and buy.price == Decimal("10.10") and portfolio.position("000001") == 10
    assert portfolio.cash == Decimal("898.90")
    sell = execute_signal(
        portfolio,
        Signal("000001", "sell", Decimal(10), "test"),
        bar,
        Decimal("0.001"),
        Decimal("0.01"),
    )
    assert sell and portfolio.position("000001") == 0


def test_suspended_or_unaffordable_trade_is_rejected() -> None:
    portfolio = Portfolio(Decimal("1"))
    signal = Signal("000001", "buy", Decimal(100), "test")
    assert (
        execute_signal(
            portfolio,
            signal,
            MarketBar(date(2026, 1, 1), "000001", Decimal(10), False),
            Decimal(0),
            Decimal(0),
        )
        is None
    )
    assert (
        execute_signal(
            portfolio,
            signal,
            MarketBar(date(2026, 1, 1), "000001", Decimal(10)),
            Decimal(0),
            Decimal(0),
        )
        is None
    )

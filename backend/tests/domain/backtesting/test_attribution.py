from datetime import date
from decimal import Decimal as D

import pytest

from easy_quant.domain.backtesting.attribution import attribute_trades
from easy_quant.domain.backtesting.entities import SimulatedTrade


def trade(symbol, action, quantity, price, fee="1"):
    return SimulatedTrade(
        date(2026, 10, 1), symbol, action, D(quantity), D(price), D(fee), D("0.01")
    )


def test_partial_sale_closed_reopened_and_fees_reconcile_to_equity():
    trades = [
        trade("a", "buy", "200", "10", "2"),
        trade("a", "sell", "100", "12"),
        trade("b", "buy", "100", "20"),
        trade("b", "sell", "100", "18"),
        trade("a", "sell", "100", "11"),
        trade("a", "buy", "100", "9"),
    ]
    rows = attribute_trades(trades, {"a": D("10")})
    assert [row.symbol for row in rows] == ["a", "b"]
    assert rows[0].quantity == 100 and rows[0].remaining_cost == 901
    assert rows[0].realized_profit == 296 and rows[0].unrealized_profit == 99
    assert rows[1].quantity == 0 and rows[1].profit == -202
    cash_delta = sum(
        (t.price * t.quantity * (1 if t.action == "sell" else -1) - t.fee for t in trades), D(0)
    )
    assert sum((row.profit for row in rows if row.profit is not None), D(0)) == cash_delta + 1000


def test_unknown_valuation_sorted_last_and_ties_use_symbol():
    rows = attribute_trades(
        [trade(s, "buy", "100", "10", "0") for s in ("z", "b", "a")], {"a": D("9"), "b": D("9")}
    )
    assert [row.symbol for row in rows] == ["a", "b", "z"]
    assert rows[-1].profit is None and rows[-1].unrealized_profit is None
    with pytest.raises(ValueError):
        attribute_trades([trade("a", "sell", "100", "10")], {})

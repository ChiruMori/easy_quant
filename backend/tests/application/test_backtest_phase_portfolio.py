from copy import deepcopy
from typing import Any, cast

import pytest

from easy_quant.application.services.backtest_runtime import execute_backtest
from easy_quant.application.services.strategy_quick_test import execute_strategy_tick
from easy_quant.domain.shared.errors import StateConflictError
from easy_quant.domain.strategies.entities import StrategyDefinition, StrategyVersion
from tests.fakes.platform import make_test_container


def prepare(source, fixed_now, *, cash="100", fee="0.001", days=2):
    container = make_test_container()
    container.market_data.upsert_bars(
        [
            {
                "symbol": "000001",
                "trading_day": f"2026-09-{21 + offset}",
                "open": "10",
                "high": "13",
                "low": "9",
                "close": "12",
                "volume": "100",
                "available_at": f"2026-09-{21 + offset}T15:00:00+08:00",
            }
            for offset in range(days)
        ]
    )
    container.state.strategies.add_definition(StrategyDefinition("s", "u", "demo"))
    container.state.strategies.add_version(StrategyVersion("v", "s", 1, source, "hash", fixed_now))
    container.state.backtests["b"] = {
        "id": "b",
        "owner_id": "u",
        "strategy_version_id": "v",
        "status": "queued",
        "config": {
            "start_day": "2026-09-21",
            "end_day": f"2026-09-{20 + days}",
            "initial_cash": cash,
            "fee_rate": fee,
            "slippage_rate": "0",
        },
    }
    return container


def test_quick_and_backtest_share_warmup_quotes_accounting_and_kv(fixed_now):
    source = """def before_market(c,p):
    c.store.set('n',c.store.get('n',0)+1)
    ma=c.factor('technical.ma',symbol='000001',window=5)
    print(c.store.get('n'),ma['available'],ma.get('value'))
    return [c.signal('000001','buy','0.2','test',price='10',lot_size=1)]
def on_market(c,p):
    print(c.store.get('n'),c.current_price('000001'),c.position('000001'))
    return [c.signal('000001','sell','0.5','test',lot_size=1)]
def after_market(c,p):
    print(c.portfolio())
    return []
"""
    container = prepare(source, fixed_now, cash="1000", fee="0.0003")
    container.market_data.upsert_bars(
        [
            {
                "symbol": "000001",
                "trading_day": f"2026-09-{day}",
                "open": "10",
                "high": "10",
                "low": "10",
                "close": "10",
                "volume": "1",
                "available_at": f"2026-09-{day}T15:00:00+08:00",
            }
            for day in range(14, 19)
        ]
    )
    quick = cast(
        dict[str, Any],
        execute_strategy_tick(
            container,
            {
                "strategy_id": "s",
                "strategy_version_id": "v",
                "owner_id": "u",
                "trading_day": "2026-09-21",
                "initial_cash": "1000",
            },
        ),
    )
    execute_backtest(container, "b")
    run = container.backtests.get("b")
    assert [phase["stdout"] for phase in quick["phase_results"]] == [
        row["text"] for row in run["strategy_outputs"][:3]
    ]
    assert run["strategy_outputs"][0]["text"] == "1 True 10\n"
    assert run["strategy_outputs"][3]["text"].startswith("2 True")
    assert quick["trades"][1]["price"] == "11.00"
    assert run["assumptions"]["warmup_start_day"] == "2026-09-14"


def test_phases_observe_executed_positions_and_decimal_cash_across_days(fixed_now):
    source = """def before_market(context, parameters):
    print(context.position("000001"), context.data["cash"])
    if context.position("000001") == 0:
        return [{"symbol": "000001", "action": "buy", "quantity": 1}]
    return []
def on_market(context, parameters):
    print(context.position("000001"), context.data["cash"])
    if context.position("000001") == 1:
        return [{"symbol": "000001", "action": "sell", "quantity": 1, "trigger_price": 11}]
    return []
def after_market(context, parameters):
    print(context.position("000001"), context.data["cash"])
    return []
"""
    container = prepare(source, fixed_now)
    execute_backtest(container, "b")
    run = container.backtests.get("b")
    assert [output["text"] for output in run["strategy_outputs"]] == [
        "0 100\n",
        "1 89.99\n",
        "0 100.98\n",
        "0 100.98\n",
        "1 90.97\n",
        "0 101.96\n",
    ]
    assert [trade["action"] for trade in run["trades"]] == ["buy", "sell", "buy", "sell"]
    assert run["periods"][-1]["cash"] == "101.96"
    assert run["assumptions"]["strategy_context_protocol"] == "strategy-library-v2"


def test_position_condition_buys_once_and_reruns_reproduce_results(fixed_now):
    source = """def before_market(context, parameters):
    if context.position("000001") == 0:
        return [{"symbol": "000001", "action": "buy", "quantity": 1}]
    return []
def on_market(context, parameters):
    return []
def after_market(context, parameters):
    return []
"""
    container = prepare(source, fixed_now, days=3)
    container.state.backtests["repeat"] = {
        **deepcopy(container.state.backtests["b"]),
        "id": "repeat",
    }
    execute_backtest(container, "b")
    execute_backtest(container, "repeat")
    first, second = container.backtests.get("b"), container.backtests.get("repeat")
    assert len(first["trades"]) == 1
    for key in ("snapshot_id", "trades", "periods", "metrics", "strategy_outputs", "assumptions"):
        assert first[key] == second[key]


@pytest.mark.parametrize(
    ("cash", "before", "on"),
    [
        ("9.99", '[{"symbol": "000001", "action": "buy", "quantity": 1}]', "[]"),
        ("100", "[]", '[{"symbol": "000001", "action": "buy", "quantity": 1, "trigger_price": 8}]'),
        (
            "100",
            "[]",
            '[{"symbol": "000001", "action": "sell", "quantity": 1, "trigger_price": 11}]',
        ),
    ],
)
def test_unexecuted_signals_do_not_change_next_phase_portfolio(fixed_now, cash, before, on):
    source = f"""def before_market(context, parameters):
    return {before}
def on_market(context, parameters):
    return {on}
def after_market(context, parameters):
    print(context.position("000001"), context.data["cash"])
    return []
"""
    container = prepare(source, fixed_now, cash=cash)
    execute_backtest(container, "b")
    run = container.backtests.get("b")
    assert run["trades"] == []
    assert [output["text"] for output in run["strategy_outputs"]] == [f"0 {cash}\n"] * 2


def test_strategy_cannot_mutate_authoritative_portfolio(fixed_now):
    source = """counter = 0
def before_market(context, parameters):
    global counter
    counter += 1
    context.data["positions"]["000001"] = "999"
    context.data["cash"] = "0"
    return [{"symbol": "000001", "action": "buy", "quantity": 1}]
def on_market(context, parameters):
    global counter
    counter += 1
    print(counter, context.position("000001"), context.data["cash"])
    context.data["positions"]["000001"] = "999"
    return [{"symbol": "000001", "action": "sell", "quantity": 1}]
def after_market(context, parameters):
    global counter
    counter += 1
    print(counter, context.position("000001"), context.data["cash"])
    return []
"""
    container = prepare(source, fixed_now, fee="0")
    execute_backtest(container, "b")
    run = container.backtests.get("b")
    assert [output["text"] for output in run["strategy_outputs"]] == [
        "2 1 90.00\n",
        "3 0 101.00\n",
        "2 1 91.00\n",
        "3 0 102.00\n",
    ]
    assert [trade["quantity"] for trade in run["trades"]] == ["1"] * 4


def test_phase_failure_does_not_publish_partial_trades(fixed_now):
    source = """def before_market(context, parameters):
    return [{"symbol": "000001", "action": "buy", "quantity": 1}]
def on_market(context, parameters):
    return 1 / 0
def after_market(context, parameters):
    return []
"""
    container = prepare(source, fixed_now)
    original = deepcopy(container.backtests.get("b"))
    with pytest.raises(StateConflictError) as error:
        execute_backtest(container, "b")
    assert error.value.details["phase"] == "on_market"
    assert container.backtests.get("b") == original

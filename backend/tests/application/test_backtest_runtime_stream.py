from datetime import date, timedelta

from easy_quant.api.blueprints.strategies import MOVING_AVERAGE_TEMPLATE
from easy_quant.application.services import backtest_runtime
from easy_quant.domain.strategies.entities import (
    StrategyDefinition,
    StrategyRun,
    StrategyRunStatus,
    StrategyVersion,
)
from tests.fakes.platform import make_test_container


def test_backtest_context_uses_bounded_history_over_many_days(monkeypatch, fixed_now) -> None:
    container = make_test_container()
    start = date(2025, 1, 1)
    days = [start + timedelta(days=index) for index in range(300)]
    container.market_data.upsert_bars(
        [
            {
                "symbol": "000001",
                "trading_day": day.isoformat(),
                "open": "10",
                "high": "11",
                "low": "9",
                "close": "10",
                "volume": "100",
                "available_at": f"{day.isoformat()}T15:00:00+08:00",
            }
            for day in days
        ]
    )
    source = (
        "def before_market(context, parameters):\n return []\n"
        "def on_market(context, parameters):\n return []\n"
        "def after_market(context, parameters):\n return []"
    )
    container.state.strategies.add_definition(StrategyDefinition("s", "u", "demo"))
    container.state.strategies.add_version(StrategyVersion("v", "s", 1, source, "hash", fixed_now))
    container.state.backtests["b"] = {
        "id": "b",
        "owner_id": "u",
        "strategy_version_id": "v",
        "config": {
            "start_day": start.isoformat(),
            "end_day": days[-1].isoformat(),
            "initial_cash": "100000",
        },
    }
    observed_bounds: list[date] = []

    class Runner:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def run_phase(self, _trading_day, *, expire_before, phase, **_kwargs):
            if phase == "before_market":
                observed_bounds.append(expire_before)
            return StrategyRun("run", "v", StrategyRunStatus.SUCCEEDED, {}, [])

    monkeypatch.setattr(backtest_runtime, "StreamingStrategyRunner", Runner)
    result = backtest_runtime.execute_backtest(container, "b")
    assert result["status"] == "succeeded"
    assert len(observed_bounds) == 300
    assert observed_bounds[-1] == days[49]
    assert len(container.backtests.get("b")["periods"]) == 300


def test_streamed_backtest_excludes_late_bars_until_they_are_available(fixed_now) -> None:
    container = make_test_container()
    days = ("2026-09-21", "2026-09-22", "2026-09-23")
    container.market_data.upsert_bars(
        [
            {
                "symbol": "000001",
                "trading_day": day,
                "open": "10",
                "high": "11",
                "low": "9",
                "close": str(10 + index),
                "volume": "100",
                "available_at": "2026-09-23T10:00:00+08:00"
                if index == 0
                else f"{day}T15:00:00+08:00",
            }
            for index, day in enumerate(days)
        ]
    )
    source = (
        "def before_market(context, parameters):\n"
        " print(len(context.factor('market.daily-bars', symbol='000001')))\n return []\n"
        "def on_market(context, parameters):\n return []\n"
        "def after_market(context, parameters):\n"
        " print(len(context.factor('market.daily-bars', symbol='000001')))\n return []"
    )
    container.state.strategies.add_definition(StrategyDefinition("s", "u", "demo"))
    container.state.strategies.add_version(StrategyVersion("v", "s", 1, source, "hash", fixed_now))
    container.state.backtests["b"] = {
        "id": "b",
        "owner_id": "u",
        "strategy_version_id": "v",
        "config": {"start_day": days[0], "end_day": days[-1], "initial_cash": "100000"},
    }
    backtest_runtime.execute_backtest(container, "b")
    outputs = container.backtests.get("b")["strategy_outputs"]
    assert [item["text"] for item in outputs if item["phase"] == "before_market"] == [
        "0\n",
        "0\n",
        "1\n",
    ]
    assert [item["text"] for item in outputs if item["phase"] == "after_market"] == [
        "0\n",
        "1\n",
        "3\n",
    ]


def test_backtest_uses_streams_and_preserves_snapshot_hash(fixed_now) -> None:
    import hashlib
    import json

    container = make_test_container()
    day = "2026-09-21"
    row = {
        "symbol": "000001",
        "trading_day": day,
        "open": "10",
        "high": "11",
        "low": "9",
        "close": "10",
        "volume": "100",
        "available_at": f"{day}T15:00:00+08:00",
    }
    container.market_data.upsert_bars([row])
    source = (
        "def before_market(context, parameters):\n return []\n"
        "def on_market(context, parameters):\n return []\n"
        "def after_market(context, parameters):\n return []"
    )
    container.state.strategies.add_definition(StrategyDefinition("s", "u", "demo"))
    container.state.strategies.add_version(StrategyVersion("v", "s", 1, source, "hash", fixed_now))
    container.state.backtests["b"] = {
        "id": "b",
        "owner_id": "u",
        "strategy_version_id": "v",
        "config": {"start_day": day, "end_day": day, "initial_cash": "100000"},
    }
    backtest_runtime.execute_backtest(container, "b")
    expected = json.dumps([row], ensure_ascii=False, sort_keys=True).encode("utf-8")
    assert container.backtests.get("b")["snapshot_id"] == hashlib.sha256(expected).hexdigest()


def test_streamed_backtest_runs_moving_average_template(fixed_now) -> None:
    container = make_test_container()
    start = date(2025, 12, 20)
    days = [start + timedelta(days=index) for index in range(43)]
    container.market_data.upsert_bars(
        [
            {
                "symbol": "000001",
                "trading_day": day.isoformat(),
                "open": str(10 + index / 100 - 0.1),
                "high": str(10 + index / 100 + 0.2),
                "low": str(10 + index / 100 - 0.2),
                "close": str(10 + index / 100),
                "volume": "100000",
                "available_at": f"{day.isoformat()}T15:00:00+08:00",
            }
            for index, day in enumerate(days)
        ]
    )
    container.state.strategies.add_definition(StrategyDefinition("s", "u", "demo"))
    container.state.strategies.add_version(
        StrategyVersion("v", "s", 1, MOVING_AVERAGE_TEMPLATE, "hash", fixed_now)
    )
    container.state.backtests["b"] = {
        "id": "b",
        "owner_id": "u",
        "strategy_version_id": "v",
        "config": {"start_day": "2026-01-01", "end_day": "2026-01-31", "initial_cash": "100000"},
    }
    assert backtest_runtime.execute_backtest(container, "b")["status"] == "succeeded"

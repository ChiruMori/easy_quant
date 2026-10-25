from datetime import date, timedelta

import pytest

from easy_quant.api.blueprints.strategies import MOVING_AVERAGE_TEMPLATE
from easy_quant.application.services import backtest_runtime
from easy_quant.application.services.run_profile import RunProfile
from easy_quant.application.services.strategy_validation import extract_history_trading_days
from easy_quant.domain.scheduling.entities import Job
from easy_quant.domain.shared.errors import StateConflictError
from easy_quant.domain.strategies.entities import (
    StrategyDefinition,
    StrategyRun,
    StrategyRunStatus,
    StrategyVersion,
)
from easy_quant.worker.handlers.backtests import register_backtest_handlers
from easy_quant.worker.registry import JobHandlerRegistry
from tests.fakes.platform import make_test_container


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("context.factor('technical.ma', window=5)", 5),
        ("context.factor('technical.ma', window=30)", 30),
        ("context.factor('technical.rsi', window=14)", 15),
        (
            "context.factor('technical.ma', window=5)\ncontext.factor('technical.rsi', window=14)",
            15,
        ),
        ("context.factor('technical.ma', window=parameters['window'])", 250),
        ("context.factor('technical.ma', **parameters)", 250),
        ("context.factor('technical.ma', window=500)\ncontext.factor('stat.expected-return')", 500),
        ("context.factor('stat.expected-return')\ncontext.factor('technical.ma', window=500)", 500),
        ("context.library('market.daily-bars')", 250),
        (MOVING_AVERAGE_TEMPLATE, 5),
        ("bars = context.library('market.daily-bars')\nprice = bars[-5]['close']", 5),
        ("bars = context.library('market.daily-bars')\nprice = bars[parameters['index']]", 250),
        ("bars = context.library('market.daily-bars')\nfor row in bars: pass", 250),
        ("context.factor('technical.macd')", 250),
        ("HISTORY_TRADING_DAYS = 100\ncontext.factor('technical.ma', window=5)", 100),
    ],
)
def test_history_inference_preserves_dynamic_and_explicit_contracts(source, expected):
    assert extract_history_trading_days(source) == expected


def setup_run(fixed_now, days):
    container = make_test_container()
    source = MOVING_AVERAGE_TEMPLATE
    container.state.strategies.add_definition(StrategyDefinition("s", "u", "demo"))
    container.state.strategies.add_version(StrategyVersion("v", "s", 1, source, "hash", fixed_now))
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
                "available_at": f"{day}T15:00:00+08:00",
            }
            for day in days
        ]
    )
    container.state.backtests["b"] = {
        "id": "b",
        "owner_id": "u",
        "strategy_version_id": "v",
        "status": "queued",
        "progress": 0,
        "config": {
            "start_day": days[5].isoformat(),
            "end_day": days[-1].isoformat(),
            "initial_cash": "100000",
        },
    }
    return container


def test_multiyear_interval_is_complete_with_only_five_day_prewarm(monkeypatch, fixed_now):
    days = [date(2020, 1, 1) + timedelta(days=index) for index in range(1831)]
    container = setup_run(fixed_now, days)
    windows = []
    stages = []
    update = container.backtests.update_status

    def record(run_id, updates):
        stages.append(updates.get("execution", {}).get("stage"))
        update(run_id, updates)

    container.backtests.update_status = record

    class Runner:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def run_phase(self, day, *, phase, expire_before, **_kwargs):
            if phase == "before_market":
                windows.append((day, expire_before))
            return StrategyRun("r", "v", StrategyRunStatus.SUCCEEDED, {}, [])

    monkeypatch.setattr(backtest_runtime, "StreamingStrategyRunner", Runner)
    backtest_runtime.execute_backtest(container, "b")
    run = container.backtests.get("b")
    assert len(run["periods"]) == 1826
    assert windows[0] == (days[5], days[0])
    assert windows[-1] == (days[-1], days[-6])
    assert run["timing"]["hooks"]["before_market"]["count"] == 1826
    assert len(run["timing"]["daily_hooks"]) == 1826 * 3
    assert {"validation", "warmup", "loading_data", "snapshot", "saving"} <= set(stages)


def test_missing_coverage_fails_before_history_read_or_strategy(monkeypatch, fixed_now):
    days = [date(2026, 9, 1) + timedelta(days=index) for index in range(8)]
    container = setup_run(fixed_now, days)
    container.state.backtests["b"]["config"]["start_day"] = "2026-08-31"
    container.state.trading_days.add("2026-08-31")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("不得读取行情或执行策略")

    monkeypatch.setattr(container.market_data, "iter_runtime_bars", forbidden)
    monkeypatch.setattr(backtest_runtime, "StreamingStrategyRunner", forbidden)
    with pytest.raises(StateConflictError) as error:
        backtest_runtime.execute_backtest(container, "b")
    assert error.value.details["missing_data"]


@pytest.mark.parametrize("inside_interval", [False, True])
def test_new_listing_does_not_require_prices_before_listing(fixed_now, inside_interval):
    days = [date(2026, 9, 1) + timedelta(days=index) for index in range(8)]
    container = setup_run(fixed_now, days)
    listing_days = days[6:] if inside_interval else [date(2027, 1, 4)]
    if inside_interval:
        container.market_data.upsert_instruments(
            [{"symbol": "000002", "listed_on": listing_days[0].isoformat()}]
        )
    container.market_data.upsert_bars(
        [
            {
                "symbol": "000002",
                "trading_day": str(day),
                "open": "10",
                "high": "11",
                "low": "9",
                "close": "10",
                "volume": "100",
                "available_at": f"{day}T15:00:00+08:00",
            }
            for day in listing_days
        ]
    )
    assert backtest_runtime.execute_backtest(container, "b")["status"] == "succeeded"


def test_failure_handler_removes_read_session_and_preserves_details(monkeypatch, fixed_now):
    days = [date(2026, 9, 1) + timedelta(days=index) for index in range(8)]
    container = setup_run(fixed_now, days)

    class Scope:
        removed = False

        def remove(self):
            self.removed = True

    scope = Scope()
    container.database_session = scope
    from easy_quant.worker.handlers import backtests

    def fail(*_args, **_kwargs):
        raise StateConflictError(
            "数据不足", {"missing_data": [{"symbol": "000001"}], "action_url": "/admin/data"}
        )

    monkeypatch.setattr(backtests, "execute_backtest", fail)
    registry = JobHandlerRegistry()
    register_backtest_handlers(registry, container)
    with pytest.raises(StateConflictError):
        registry.get("backtest.run")(Job("j", "backtest.run", "b", {"backtest_id": "b"}, fixed_now))
    run = container.backtests.get("b")
    assert scope.removed
    assert run["status"] == "failed" and run["error"] == "数据不足"
    assert run["error_details"]["missing_data"] == [{"symbol": "000001"}]
    assert "validation" in run["timing"]["stages"]


def test_profile_hook_statistics_use_injected_time():
    values = iter([0.0, 1.0, 2.0, 5.0, 7.0])
    profile = RunProfile(lambda: next(values))
    profile.enter("strategy")
    profile.record_hook("2026-10-09", "before_market", 1.0)
    profile.record_hook("2026-10-12", "before_market", 2.0)
    result = profile.snapshot()
    assert result["total_seconds"] == 7
    assert result["stages"] == {"validation": 1, "strategy": 6}
    assert result["hooks"]["before_market"] == {
        "count": 2,
        "total_seconds": 4,
        "average_seconds": 2,
        "max_seconds": 3,
    }

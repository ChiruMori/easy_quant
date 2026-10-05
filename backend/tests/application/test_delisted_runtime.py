from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from easy_quant.application.services import backtest_runtime, live_runtime, strategy_quick_test
from easy_quant.domain.strategies.entities import (
    Signal,
    StrategyDefinition,
    StrategyRun,
    StrategyRunStatus,
    StrategyVersion,
)
from tests.fakes.live_tracking import action_container
from tests.fakes.platform import make_test_container


def _bar(symbol: str) -> dict[str, str]:
    return {
        "symbol": symbol,
        "trading_day": "2026-09-29",
        "open": "10",
        "high": "11",
        "low": "9",
        "close": "10",
        "volume": "100",
        "available_at": "2026-09-29T15:00:00+08:00",
    }


def _prepare(container, fixed_now) -> None:
    container.market_data.upsert_instruments(
        [
            {
                "symbol": "000001",
                "name": "在市股票",
                "exchange": "深圳证券交易所",
                "status": "active",
            },
            {
                "symbol": "000002",
                "name": "退市股票",
                "exchange": "深圳证券交易所",
                "status": "delisted",
            },
            {
                "symbol": "000003",
                "name": "停牌股票",
                "exchange": "深圳证券交易所",
                "status": "suspended",
            },
        ]
    )
    container.market_data.upsert_bars([_bar("000001"), _bar("000002"), _bar("000003")])
    container.state.strategies.add_definition(StrategyDefinition("s", "u", "demo"))
    container.state.strategies.add_version(
        StrategyVersion(
            "v", "s", 1, "def before_market(context, parameters):\n return []", "hash", fixed_now
        )
    )


def _signals() -> list[Signal]:
    return [Signal("000002", "buy", Decimal(1), "hardcoded")]


def test_quick_test_excludes_delisted_bars_and_hardcoded_signals(monkeypatch, fixed_now) -> None:
    container = make_test_container()
    _prepare(container, fixed_now)
    contexts = []

    class Runner:
        def __init__(self, *_args, **_kwargs):
            pass

        def run_many(self, _version, _parameters, values):
            contexts.extend(context for context, _phase in values)
            return [
                StrategyRun("run", "v", StrategyRunStatus.SUCCEEDED, {}, _signals()) for _ in values
            ]

    monkeypatch.setattr(strategy_quick_test, "SubprocessStrategyRunner", Runner)
    result = strategy_quick_test.execute_strategy_tick(
        container,
        {
            "strategy_id": "s",
            "strategy_version_id": "v",
            "owner_id": "u",
            "trading_day": "2026-09-29",
        },
    )
    assert all("000002" not in context["universe"] for context in contexts)
    assert all("000003" not in context["universe"] for context in contexts)
    assert contexts[1]["universe"] == ["000001"]
    phase_results = result["phase_results"]
    assert isinstance(phase_results, list)
    assert all(isinstance(item, dict) and item["signals"] == [] for item in phase_results)


def test_backtest_excludes_delisted_bars_and_hardcoded_signals(monkeypatch, fixed_now) -> None:
    container = make_test_container()
    _prepare(container, fixed_now)
    container.state.backtests["b"] = {
        "id": "b",
        "owner_id": "u",
        "strategy_version_id": "v",
        "config": {"start_day": "2026-09-29", "end_day": "2026-09-29", "initial_cash": "100000"},
    }
    observed = []

    class Runner:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def run_day(self, _trading_day, **kwargs):
            observed.append(kwargs["today_symbols"])
            return [
                StrategyRun("run", "v", StrategyRunStatus.SUCCEEDED, {}, _signals())
                for _ in range(3)
            ]

    monkeypatch.setattr(backtest_runtime, "StreamingStrategyRunner", Runner)
    backtest_runtime.execute_backtest(container, "b")
    run = container.backtests.get("b")
    assert observed == [["000001", "000003"]]
    assert run["trades"] == []
    assert run["assumptions"]["excluded_delisted_symbols"] == ["000002"]
    expected = json.dumps(
        [_bar("000001"), _bar("000003")], ensure_ascii=False, sort_keys=True
    ).encode("utf-8")
    assert run["snapshot_id"] == hashlib.sha256(expected).hexdigest()


def test_live_excludes_delisted_prices_and_hardcoded_signals(monkeypatch, fixed_now) -> None:
    container = action_container()
    _prepare(container, fixed_now)
    contexts = []

    class Runner:
        def __init__(self, *_args, **_kwargs):
            pass

        def run(self, _version, _parameters, context, *, phase):
            contexts.append(context)
            return StrategyRun("run", "v", StrategyRunStatus.SUCCEEDED, {}, _signals())

    monkeypatch.setattr(live_runtime, "SubprocessStrategyRunner", Runner)
    result = live_runtime.analyze_live_instance(
        container,
        "l",
        "before_market",
        fixed_now,
        {"000001": "10", "000002": "10", "000003": "10"},
    )
    assert contexts[0]["universe"] == ["000001"]
    assert contexts[0]["current_prices"] == {"000001": "10"}
    assert result["created"] == []

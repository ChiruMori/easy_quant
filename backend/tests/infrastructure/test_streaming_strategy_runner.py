from datetime import date

from easy_quant.domain.strategies.entities import StrategyRunStatus, StrategyVersion
from easy_quant.infrastructure.strategy_runtime.runner import StreamingStrategyRunner


def _version(source: str, fixed_now) -> StrategyVersion:
    return StrategyVersion("v", "s", 1, source, "hash", fixed_now)


def _run_day(runner: StreamingStrategyRunner, day: date, *, close: str):
    return runner.run_day(
        day,
        expire_before=date(2026, 9, 1),
        prior_before=[],
        prior_after=[],
        today_after=[{"symbol": "000001", "trading_day": day.isoformat(), "close": close}],
        today_symbols=["000001"],
        current_prices={"000001": float(close)},
    )


def test_streaming_runner_reuses_history_but_resets_strategy_globals(fixed_now) -> None:
    source = (
        "counter = 0\n"
        "def before_market(context, parameters):\n"
        " global counter\n counter += 1\n"
        " print(counter, context.factor('technical.ma', symbol='000001', window=1)['available'])\n"
        " return []\n"
        "def on_market(context, parameters):\n return []\n"
        "def after_market(context, parameters):\n return []"
    )
    with StreamingStrategyRunner(_version(source, fixed_now), {}) as runner:
        first = _run_day(runner, date(2026, 9, 1), close="10")
        second = _run_day(runner, date(2026, 9, 2), close="11")
    assert all(result.status is StrategyRunStatus.SUCCEEDED for result in first + second)
    assert first[0].stdout == "1 False\n"
    assert second[0].stdout == "1 True\n"


def test_streaming_runner_times_out_and_reaps_child(fixed_now) -> None:
    source = "def before_market(context, parameters):\n while True: pass"
    with StreamingStrategyRunner(_version(source, fixed_now), {}, timeout_seconds=1) as runner:
        results = _run_day(runner, date(2026, 9, 1), close="10")
    assert all(result.status is StrategyRunStatus.TIMED_OUT for result in results)


def test_phase_protocol_rejects_out_of_order_hooks_and_keeps_history_isolation(fixed_now):
    source = (
        "def before_market(context, parameters):\n"
        " print(len(context.factor('market.daily-bars', symbol='000001')))\n return []\n"
        "def on_market(context, parameters):\n"
        " print(len(context.factor('market.daily-bars', symbol='000001')))\n return []\n"
        "def after_market(context, parameters):\n"
        " print(len(context.factor('market.daily-bars', symbol='000001')))\n return []"
    )
    day = date(2026, 9, 21)
    arguments = {
        "expire_before": day,
        "prior_before": [],
        "prior_after": [],
        "today_after": [{"symbol": "000001", "trading_day": day.isoformat(), "close": "10"}],
        "today_symbols": ["000001"],
        "current_prices": {"000001": 10.0},
        "positions": {},
        "cash": "100",
    }
    with StreamingStrategyRunner(_version(source, fixed_now), {}) as runner:
        invalid = runner.run_phase(day, phase="on_market", **arguments)
        before = runner.run_phase(day, phase="before_market", **arguments)
        skipped = runner.run_phase(day, phase="after_market", **arguments)
        on = runner.run_phase(day, phase="on_market", **arguments)
        after = runner.run_phase(day, phase="after_market", **arguments)
        replay = runner.run_phase(day, phase="before_market", **arguments)
    assert all(result.status is StrategyRunStatus.FAILED for result in (invalid, skipped, replay))
    assert all(result.status is StrategyRunStatus.SUCCEEDED for result in (before, on, after))
    assert [result.stdout for result in (before, on, after)] == ["0\n", "0\n", "1\n"]


def test_single_phase_timeout_reaps_child(fixed_now):
    source = "def before_market(context, parameters):\n while True: pass"
    with StreamingStrategyRunner(_version(source, fixed_now), {}, timeout_seconds=1) as runner:
        result = runner.run_phase(
            date(2026, 9, 21),
            phase="before_market",
            expire_before=date(2026, 9, 1),
            prior_before=[],
            prior_after=[],
            today_after=[],
            today_symbols=[],
            current_prices={},
            positions={},
            cash="100",
        )
        assert runner._process.poll() is not None
    assert result.status is StrategyRunStatus.TIMED_OUT

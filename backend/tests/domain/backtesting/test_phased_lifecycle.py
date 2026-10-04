from datetime import date, timedelta
from decimal import Decimal

from easy_quant.domain.backtesting.engine import PhasedBacktestSession, run_phased_daily_backtest
from easy_quant.domain.backtesting.entities import BacktestConfig
from easy_quant.domain.backtesting.execution import MarketBar
from easy_quant.domain.strategies.entities import Signal


def test_each_trading_day_runs_three_hooks_in_order_without_notification() -> None:
    phases: list[tuple[date, str]] = []
    config = BacktestConfig(
        "version",
        ("000001",),
        date(2026, 9, 29),
        date(2026, 9, 30),
        Decimal("100000"),
    )
    bars = [
        MarketBar(date(2026, 9, 29), "000001", Decimal("10")),
        MarketBar(date(2026, 9, 30), "000001", Decimal("11")),
    ]

    periods, trades, _ = run_phased_daily_backtest(
        config, bars, lambda day, phase: phases.append((day, phase)) or []
    )

    assert phases == [
        (date(2026, 9, 29), "before_market"),
        (date(2026, 9, 29), "on_market"),
        (date(2026, 9, 29), "after_market"),
        (date(2026, 9, 30), "before_market"),
        (date(2026, 9, 30), "on_market"),
        (date(2026, 9, 30), "after_market"),
    ]
    assert len(periods) == 2
    assert trades == []


def test_phase_execution_uses_open_trigger_and_close_prices() -> None:
    config = BacktestConfig(
        "version",
        ("000001",),
        date(2026, 9, 29),
        date(2026, 9, 29),
        Decimal("100000"),
    )
    bar = MarketBar(
        date(2026, 9, 29),
        "000001",
        Decimal("11"),
        True,
        Decimal("10"),
        Decimal("12"),
        Decimal("9"),
    )

    def strategy(_day: date, phase: str) -> list[Signal]:
        if phase == "before_market":
            return [Signal("000001", "buy", Decimal(100), "盘前买入")]
        if phase == "on_market":
            return [
                Signal("000001", "sell", Decimal(100), "盘中止盈", Decimal("11.5")),
                Signal("000001", "buy", Decimal(100), "未触发", Decimal("8")),
            ]
        return []

    _, trades, _ = run_phased_daily_backtest(config, [bar], strategy)

    assert [trade.price for trade in trades] == [Decimal("10.00"), Decimal("11.50")]


def test_incremental_engine_handles_multi_year_sequence_without_bars_list() -> None:
    start = date(2020, 1, 1)
    end = start + timedelta(days=999)
    session = PhasedBacktestSession(
        BacktestConfig("version", ("000001",), start, end, Decimal("100000"))
    )
    for offset in range(1000):
        day = start + timedelta(days=offset)
        session.advance(day, [MarketBar(day, "000001", Decimal("10"))], lambda _phase: [])
    periods, trades, metrics = session.finish()
    assert len(periods) == 1000
    assert trades == []
    assert metrics["trade_count"] == 0

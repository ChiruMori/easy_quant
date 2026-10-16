from datetime import date
from decimal import Decimal

import pytest

from easy_quant.application.services.backtest_runtime import execute_backtest
from easy_quant.application.services.market_data_sync import MarketDataSyncService
from easy_quant.domain.backtesting.entities import Portfolio
from easy_quant.domain.backtesting.execution import MarketBar, execute_signal
from easy_quant.domain.live_tracking.ledger import (
    ActualOperation,
    OperationKind,
    entry_for_operation,
)
from easy_quant.domain.shared.errors import StateConflictError
from easy_quant.domain.strategies.entities import Signal, StrategyDefinition, StrategyVersion
from easy_quant.strategy_api.context import RuntimeContext
from tests.application.test_market_data_sync import FakeAcquisition
from tests.fakes.platform import make_test_container


def seeded(fixed_now):
    container = make_test_container()
    source = """def before_market(context, parameters):
    return [{"symbol": "sh000300", "action": "buy", "quantity": "1", "reason": "blocked"}]
def on_market(context, parameters):
    return []
def after_market(context, parameters):
    print(context.factor("technical.ma", symbol="sh000300", window=1))
    return []
"""
    container.state.strategies.add_definition(StrategyDefinition("s", "u", "指数查询"))
    container.state.strategies.add_version(StrategyVersion("v", "s", 1, source, "hash", fixed_now))
    container.state.backtests["b"] = {
        "id": "b",
        "owner_id": "u",
        "strategy_version_id": "v",
        "config": {
            "start_day": "2026-09-28",
            "end_day": "2026-09-29",
            "initial_cash": "1000",
            "benchmark": "000300",
        },
    }
    container.market_data.upsert_bars(
        [
            {
                "symbol": symbol,
                "trading_day": day,
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": "100",
                "available_at": f"{day}T15:00:00+08:00",
            }
            for symbol in ("000001", "sh000300")
            for day, close in (("2026-09-28", "100"), ("2026-09-29", "110"))
        ]
    )
    return container


def test_benchmark_curve_and_index_history_without_trades(fixed_now):
    container = seeded(fixed_now)
    execute_backtest(container, "b")
    run = container.backtests.get("b")
    assert run["metrics"]["benchmark_return"] == "0.1"
    assert run["benchmark"] == {"symbol": "sh000300", "name": "沪深300"}
    assert [row["benchmark_equity"] for row in run["periods"]] == ["1000", "1100"]
    assert run["trades"] == []
    assert run["strategy_outputs"]


@pytest.mark.parametrize("late", [False, True])
def test_missing_or_not_yet_available_benchmark_blocks_run(fixed_now, late):
    container = seeded(fixed_now)
    rows = container.market_data.daily_bars
    for key in list(rows):
        if rows[key]["symbol"] == "sh000300":
            if late:
                rows[key]["available_at"] = "2026-09-30T15:00:00+08:00"
            else:
                del rows[key]
    with pytest.raises(StateConflictError, match="基准行情"):
        execute_backtest(container, "b")


def test_indices_never_trade_even_when_directly_signalled(fixed_now):
    signal = Signal("sh000300", "buy", Decimal(1), "test")
    assert (
        execute_signal(
            Portfolio(Decimal(1000)),
            signal,
            MarketBar(date(2026, 9, 29), "sh000300", Decimal(100)),
            Decimal(0),
            Decimal(0),
        )
        is None
    )
    with pytest.raises(StateConflictError):
        entry_for_operation(
            "e",
            "l",
            ActualOperation(
                "o",
                "r",
                "u",
                OperationKind.CORRECT,
                "k",
                fixed_now,
                "sh000300",
                "buy",
                Decimal(1),
                Decimal(100),
            ),
        )
    context = RuntimeContext({"universe": ["000001", "sh000300"], "prices": {"sh000300": ["100"]}})
    assert context.universe() == ["000001"]
    assert context.factor("technical.ma", symbol="sh000300", window=1)["value"] == Decimal(100)


def test_index_catalog_and_sync_preserve_namespace_and_no_adjustment():
    container = make_test_container()
    securities = FakeAcquisition([{"code": "000001", "name": "平安银行"}])
    daily = FakeAcquisition(
        [{"日期": "2026-09-29", "开盘": 100, "最高": 101, "最低": 99, "收盘": 100, "成交量": 200}]
    )
    service = MarketDataSyncService(
        {"securities": securities, "daily-bars": daily}, container.market_data
    )
    service.sync("securities")
    assert container.market_data.get_instrument("sh000001")["name"] == "上证指数"
    assert container.market_data.get_instrument("000001")["name"] == "平安银行"
    service.sync(
        "daily-bars", symbols=["sh000300"], start_day=date(2026, 9, 29), end_day=date(2026, 9, 29)
    )
    assert daily.requests[0].parameters["adjustment"] == "none"
    assert container.market_data.list_bars(symbol="sh000300")[0]["adjustment"] == "none"


def test_index_catalog_cannot_mask_invalid_stock_catalog():
    container = make_test_container()
    container.market_data.upsert_instruments(
        [{"symbol": "000001", "name": "平安银行", "status": "active"}]
    )
    service = MarketDataSyncService(
        {"securities": FakeAcquisition([{"code": "bad"}])}, container.market_data
    )
    with pytest.raises(ValueError, match="缺少在市股票"):
        service.sync("securities")
    assert container.market_data.get_instrument("000001")["status"] == "active"

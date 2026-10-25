from datetime import UTC, datetime
from decimal import Decimal

from easy_quant.application.services.strategy_validation import (
    extract_factor_dependencies,
    extract_history_trading_days,
)
from easy_quant.factors.context import FactorContext
from easy_quant.factors.registry import build_default_registry
from easy_quant.platform_library.catalog import build_library_registry
from easy_quant.strategy_api.context import RuntimeContext


def test_catalogs_separate_raw_data_and_computation():
    assert {item.key for item in build_default_registry().list()} == {
        "technical.ma",
        "technical.rsi",
        "technical.macd",
        "stat.expected-return",
    }
    assert {item.key for item in build_library_registry().list()} == {
        "market.daily-bars",
        "market.value",
        "fundamental.latest",
        "fundamental.history",
    }


def test_source_snapshot_is_read_once_and_results_are_isolated():
    class Gateway:
        calls = 0

        def records(self, dataset, symbol):
            self.calls += 1
            return [
                {"close": Decimal(10), "available_at": datetime(2026, 1, 1, tzinfo=UTC)},
                {"close": Decimal(999), "available_at": datetime(2026, 1, 3, tzinfo=UTC)},
            ]

    gateway = Gateway()
    context = FactorContext(gateway, datetime(2026, 1, 2, tzinfo=UTC))
    factors = build_default_registry()
    first = factors.call("technical.ma", context, {"symbol": "a", "window": 1})
    assert isinstance(first, dict)
    first["value"] = Decimal(0)
    second = factors.call("technical.ma", context, {"symbol": "a", "window": 1})
    assert isinstance(second, dict)
    assert second["value"] == 10
    records = context.read("daily-bars", "a")
    assert isinstance(records[0], dict)
    records[0]["close"] = Decimal(100)
    assert context.read("daily-bars", "a")[0]["close"] == 10
    assert gateway.calls == 1


def test_library_runtime_and_legacy_route_have_same_visible_data():
    context = RuntimeContext(
        {"decision_at": "2026-01-02T00:00:00+00:00", "prices": {"a": ["10", "12"]}}
    )
    assert context.library("market.daily-bars", symbol="a") == context.factor(
        "market.daily-bars", symbol="a"
    )
    assert context.factor("technical.ma", symbol="a", window=2)["value"] == Decimal(11)
    source = "bars = context.library('market.daily-bars', symbol='a')\nprice = bars[-20]['close']"
    assert extract_history_trading_days(source) == 20
    assert extract_factor_dependencies(source) == {"daily-bars"}
    assert extract_factor_dependencies(
        "context.library('fundamental.history', symbol='a', dataset='financial-indicators')"
    ) == {"financial-indicators"}

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

import pytest

from easy_quant.domain.strategies.entities import StrategyRunStatus, StrategyVersion
from easy_quant.factors.context import FactorContext
from easy_quant.factors.registry import build_default_registry
from easy_quant.infrastructure.strategy_runtime.runner import SubprocessStrategyRunner
from easy_quant.strategy_api.context import RuntimeContext, SnapshotGateway


@pytest.mark.parametrize(
    "key,parameters",
    [
        ("technical.ma", {"window": 5}),
        ("technical.rsi", {"window": 14}),
        ("technical.macd", {}),
        ("stat.expected-return", {}),
    ],
)
def test_subprocess_uses_same_decimal_factor_as_platform(key, parameters, fixed_now):
    data: dict[str, Any] = {
        "prices": {"x": [str(Decimal(10) + Decimal(index) / 10) for index in range(40)]}
    }
    expected = build_default_registry().call(
        key,
        FactorContext(SnapshotGateway(data), datetime(9999, 12, 31, tzinfo=UTC)),
        {"symbol": "x", **parameters},
    )
    source = f"def before_market(c,p):\n print(c.factor({key!r},symbol='x',**p)); return []"
    run = SubprocessStrategyRunner().run(
        StrategyVersion("v", "s", 1, source, "h", fixed_now),
        parameters,
        data,
    )
    assert run.status is StrategyRunStatus.SUCCEEDED
    assert run.stdout.strip() == str(expected)
    assert "Decimal" in run.stdout


def test_partial_sizing_decimal_fees_and_budget_are_respected():
    context = RuntimeContext({"cash": "100000", "positions": {"x": "1000"}})
    buy = context.signal("x", "buy", "0.1", "配置仓位", price="10")
    sell = context.signal("x", "sell", "0.5", "降低风险")
    assert buy["quantity"] == Decimal(900)
    assert sell["quantity"] == Decimal(500)
    assert buy["ratio"] == Decimal("0.1") and buy["ratio_basis"] == Decimal(100000)
    assert context.position("x") == Decimal(1000)
    with pytest.raises(ValueError):
        context.signal("x", "buy", "NaN", "bad", price=10)
    with pytest.raises(ValueError):
        context.signal("x", "sell", "1.1", "bad")
    assert context.signal("x", "sell", "0.6", "超额")["quantity"] == 0


def test_kv_returns_copies_and_rejects_oversized_values():
    context = RuntimeContext({})
    context.store.set("items", ["x"])
    copied = context.store.get("items")
    copied.append("y")
    assert context.store.get("items") == ["x"]
    context.store.set("price", Decimal("1.01"))
    assert context.store.get("price") == "1.01"
    with pytest.raises(ValueError, match="256"):
        context.store.set("large", "x" * (256 * 1024))
    context.store.delete("items")
    assert context.store.get("items") is None


def test_industry_universe_includes_known_new_listing_without_price_history():
    data = {
        "universe": [],
        "trading_day": "2026-09-29",
        "decision_at": "2026-09-29T01:00:00+00:00",
        "records": {
            "security-status": {
                "new": [
                    {
                        "symbol": "new",
                        "status": "active",
                        "listed_on": "2026-09-29",
                        "available_at": "2026-09-28T14:00:00+00:00",
                    }
                ],
                "future": [
                    {
                        "symbol": "future",
                        "status": "active",
                        "listed_on": "2026-09-30",
                        "available_at": "2026-09-28T14:00:00+00:00",
                    }
                ],
            },
            "sw-industry-memberships": {
                "new": [
                    {
                        "symbol": "new",
                        "industry_code": "801010",
                        "available_at": "2026-09-28T14:00:00+00:00",
                    }
                ],
            },
        },
    }
    assert RuntimeContext(data).securities("801010") == ["new"]


def test_live_subprocess_quotes_only_requested_symbols_and_caches(fixed_now):
    source = """def on_market(c,p):
    print(c.quotes(['000001', '600001']))
    print(c.current_price('000001'))
    c.store.set('limit', Decimal('10.5'))
    return []
"""
    requests = []

    def quotes(symbols: list[str]) -> dict[str, object]:
        requests.append(symbols)
        return {symbol: "10.50" for symbol in symbols}

    run = SubprocessStrategyRunner().run_live(
        StrategyVersion("v", "s", 1, source, "h", fixed_now),
        {},
        {"phase": "on_market"},
        phase="on_market",
        quotes=quotes,
    )
    assert run.status is StrategyRunStatus.SUCCEEDED
    assert requests == [["000001", "600001"]]
    assert run.state == {"limit": "10.5"}
    assert "Decimal('10.50')" in run.stdout


def test_mock_is_explicit_deterministic_and_unavailable_to_real_runtimes():
    base = {"prices": {"x": ["10", "11"]}, "allow_mock": True}
    for runtime in ("backtest", "live"):
        result = RuntimeContext({**base, "runtime": runtime}).factor(
            "technical.ma", symbol="x", window=30
        )
        assert not result["available"]
    quick = RuntimeContext({**base, "runtime": "quick_test"})
    result = quick.factor("technical.ma", symbol="x", window=30)
    assert result["available"] and isinstance(result["value"], Decimal)
    assert quick.mock_usage == [{"factor": "technical.ma", "symbol": "x", "count": 28}]


def test_future_finance_is_hidden_and_history_is_sorted():
    context = RuntimeContext(
        {
            "decision_at": "2026-09-29T09:00:00+08:00",
            "records": {
                "financial-indicators": {
                    "x": [
                        {"available_at": "2026-09-30T00:00:00+08:00", "roe": "30"},
                        {"available_at": "2026-09-28T00:00:00+08:00", "roe": "12"},
                        {"available_at": "2026-09-27T00:00:00+08:00", "roe": "10"},
                    ]
                }
            },
        }
    )
    assert [row["roe"] for row in cast(list[dict[str, Any]], context.financials("x"))] == [
        Decimal(10),
        Decimal(12),
    ]

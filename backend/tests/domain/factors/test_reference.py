import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from easy_quant.application.services.strategy_validation import (
    extract_factor_dependencies,
    extract_history_trading_days,
)
from easy_quant.factors.alpha101 import Frame
from easy_quant.factors.reference import references
from easy_quant.factors.series import Unavailable, number
from easy_quant.strategy_api.context import RuntimeContext


@pytest.fixture(scope="module")
def context():
    bars = {}
    for offset, symbol in enumerate(("000001", "000002", "000003", "sh000001", "sh000300")):
        rows = []
        for i in range(1400):
            day = date(2020, 1, 1) + timedelta(days=i)
            close = Decimal(20) + Decimal(i) / 100 + Decimal((i + offset) % 3)
            volume = Decimal(1000 + ((2 * i + offset) % 3) * 100 + i % 7)
            rows.append(
                {
                    "trading_day": day.isoformat(),
                    "available_at": f"{day}T15:00:00+00:00",
                    "open": str(close - Decimal(".2") + Decimal(i % 3) / 10),
                    "high": str(close + 1 + Decimal(i % 5) / 10),
                    "low": str(close - 1 - Decimal(i % 7) / 10),
                    "close": str(close),
                    "volume": str(volume),
                    "amount": str(volume * close),
                }
            )
        bars[symbol] = rows
    return RuntimeContext(
        {
            "bars": bars,
            "decision_at": "2026-01-01T00:00:00+00:00",
            "records": {
                "market-values": {
                    s: [
                        {
                            "market_cap": str(1000000 * (i + 1)),
                            "circulating_market_cap": str(500000 * (i + 1)),
                            "available_at": "2020-01-01T00:00:00+00:00",
                        }
                    ]
                    for i, s in enumerate(("000001", "000002", "000003"))
                }
            },
        }
    )


@pytest.mark.parametrize("entry", references(), ids=lambda item: item.key)
def test_each_reference_is_registered_evaluates_and_declares_full_prewarm(entry, context):
    source = f"context.factor('{entry.key}', symbol='000001')"
    assert extract_history_trading_days(source) == entry.history
    assert extract_factor_dependencies(source) == set(entry.datasets)
    result = context.factor(entry.key, symbol="000001", symbols=["000001", "000002", "000003"])
    # 此样本有变化的价格/成交量与完整指数，每个已实现入口都必须实际产出。
    assert result["available"], (entry.key, result)
    assert isinstance(result["value"], Decimal) and result["value"].is_finite()


def test_catalog_accounts_for_each_public_item_once():
    inventory = json.loads(
        (Path(__file__).parents[4] / "specs/036-reference-factor-catalog/inventory.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(inventory) == len({item["name"] for item in inventory}) == 202
    implemented = {entry.key for entry in references()}
    assert len(implemented) == 85
    assert {item["name"] for item in inventory if item["status"] == "implemented"} == implemented
    assert all(
        item["reason"] and item["required_changes"]
        for item in inventory
        if item["status"] == "blocked"
    )


def test_returns_amount_ma_and_alpha101_have_hand_computable_values():
    rows = [
        {
            "trading_day": f"2026-01-{i + 1:02}",
            "available_at": "2026-01-30T00:00:00+00:00",
            "open": "9",
            "close": str(10 + i),
            "high": "31",
            "low": "8",
            "volume": str(100 + i),
            "amount": str(1000 + i * 100),
        }
        for i in range(21)
    ]
    runtime = RuntimeContext({"bars": {"a": rows}, "decision_at": "2026-02-01T00:00:00+00:00"})
    assert runtime.factor("return_5d", symbol="a")["value"] == Decimal(30) / 25 - 1
    assert runtime.factor("ma_20d", symbol="a")["value"] == Decimal("20.5")
    assert runtime.factor("amount_ma_20d", symbol="a")["value"] == Decimal(2050)
    assert runtime.factor("alpha101_101", symbol="a")["value"] == Decimal(21) / Decimal("23.001")
    assert runtime.factor("alpha101_12", symbol="a")["value"] == -1
    assert runtime.factor("alpha101_9", symbol="a")["value"] == 1
    assert (
        runtime.factor("alpha101_41", symbol="a")["value"]
        == Decimal(248).sqrt() - Decimal(3000) / 120
    )
    assert runtime.factor("alpha101_54", symbol="a")["value"] == -Decimal(-22) * Decimal(9) ** 5 / (
        Decimal(-23) * Decimal(30) ** 5
    )


def test_cross_section_rank_ties_and_missing_dates():
    frame = Frame(
        {"a": [Decimal(1), None], "b": [Decimal(1), Decimal(3)], "c": [Decimal(3), Decimal(1)]}
    )
    assert frame.rank().values == {
        "a": [Decimal(".5"), None],
        "b": [Decimal(".5"), Decimal(1)],
        "c": [Decimal(1), Decimal(".5")],
    }
    # 首个最大值的位置从1起；缺样本不得缩短窗口。
    assert frame.roll(2, max).values["a"] == [None, None]


def test_regression_matches_known_line_and_rejects_date_gaps():
    stock = Decimal(100)
    index = Decimal(100)
    a, b = [], []
    for i in range(61):
        if i:
            x = Decimal(i % 7 - 3) / 1000
            index *= 1 + x
            stock *= 1 + Decimal(".001") + 2 * x
        day = (date(2026, 1, 1) + timedelta(days=i)).isoformat()
        for output, close in ((a, stock), (b, index)):
            output.append(
                {
                    "trading_day": day,
                    "available_at": "2026-04-01T00:00:00+00:00",
                    "close": str(close),
                }
            )
    runtime = RuntimeContext(
        {"bars": {"a": a, "sh000300": b}, "decision_at": "2026-05-01T00:00:00+00:00"}
    )
    assert abs(runtime.factor("beta_60d_000300", symbol="a")["value"] - 2) < Decimal("1e-22")
    b[-2] = {**b[-2], "trading_day": "2026-03-05"}
    runtime = RuntimeContext(
        {"bars": {"a": a, "sh000300": b}, "decision_at": "2026-05-01T00:00:00+00:00"}
    )
    assert runtime.factor("beta_60d_000300", symbol="a") == {
        "available": False,
        "reason": "unaligned_dates",
    }


def test_wilder_rsi_is_not_simple_moving_average(context):
    rows = context.data["bars"]["000001"]
    closes = [Decimal(row["close"]) for row in rows]
    gain = max(closes[1] - closes[0], Decimal(0))
    loss = max(closes[0] - closes[1], Decimal(0))
    for a, b in zip(closes[1:], closes[2:], strict=False):
        change = b - a
        gain = (gain * 13 + max(change, Decimal(0))) / 14
        loss = (loss * 13 + max(-change, Decimal(0))) / 14
    expected = 100 - 100 / (1 + gain / loss)
    assert abs(context.factor("rsi", symbol="000001")["value"] - expected) < Decimal("1e-23")


def test_future_missing_fields_zero_denominator_and_universe_are_explicit(context):
    assert context.factor("alpha101_3", symbol="000001")["reason"] == "explicit_universe_required"
    runtime = RuntimeContext(
        {
            "bars": {"a": [{"close": "10", "available_at": "2026-03-01T00:00:00+00:00"}]},
            "decision_at": "2026-01-01T00:00:00+00:00",
        }
    )
    assert not runtime.factor("log_price", symbol="a")["available"]
    runtime = RuntimeContext(
        {"prices": {"a": ["10"] * 61}, "decision_at": "2026-01-01T00:00:00+00:00"}
    )
    assert runtime.factor("sharpe_60d", symbol="a")["reason"] == "zero_denominator"
    assert not runtime.factor("alpha101_41", symbol="a")["available"]
    with pytest.raises(Unavailable):
        number("NaN")


@pytest.mark.parametrize(
    "entry",
    [
        item
        for item in references()
        if item.key.startswith(("alpha_", "beta_", "sigma_", "volume_alpha_", "volume_beta_"))
    ],
    ids=lambda item: item.key,
)
def test_each_regression_factor_obeys_identical_series_identity(entry, context):
    rows = context.data["bars"]["000001"]
    runtime = RuntimeContext(
        {
            "bars": {"a": rows, "sh000001": rows, "sh000300": rows},
            "decision_at": "2026-01-01T00:00:00+00:00",
        }
    )
    value = runtime.factor(entry.key, symbol="a")["value"]
    expected = (
        1
        if entry.key.startswith(("beta_", "volume_beta_")) and "consistency" not in entry.key
        else 0
    )
    assert abs(value - expected) < Decimal("1e-23")


def test_population_std_sharpe_high_low_and_price_distance():
    runtime = RuntimeContext(
        {"prices": {"a": ["10", "12", "9"] * 21}, "decision_at": "2026-01-01T00:00:00+00:00"}
    )
    # 21日收益样本由 1/9、1/5、-1/4 各7项组成。
    sample = [Decimal(1) / 9, Decimal(1) / 5, -Decimal(1) / 4]
    average = sum(sample, Decimal(0)) / Decimal(3)
    deviation = (
        sum(((v - average) * (v - average) for v in sample), Decimal(0)) / Decimal(3)
    ).sqrt()
    assert abs(runtime.factor("return_std_21d", symbol="a")["value"] - deviation) < Decimal("1e-25")
    assert runtime.factor("high_low_21d", symbol="a")["value"] == Decimal(12) / 9
    assert runtime.factor("price_dist", symbol="a")["value"] == 1


def test_reference_does_not_silently_ignore_parameter_overrides(context):
    from easy_quant.domain.shared.errors import ValidationError

    with pytest.raises(ValidationError):
        context.factor("return_21d", symbol="000001", window=5)

from copy import deepcopy
from decimal import Decimal

import pytest

from easy_quant.application.services.chart_comparisons import (
    comparison_candidates,
    comparison_series,
    search_instruments,
)
from easy_quant.domain.shared.errors import NotFoundError, StateConflictError, ValidationError
from tests.fakes.live_tracking import action_container


def setup():
    c = action_container()
    config = {
        "start_day": "2026-09-28",
        "end_day": "2026-09-29",
        "initial_cash": "1000",
        "initial_positions": {},
    }
    for identifier, owner, value in (
        ("main", "u", "1050"),
        ("other", "u", "1100"),
        ("private", "other", "1200"),
    ):
        c.backtests.rows[identifier] = {
            "id": identifier,
            "owner_id": owner,
            "status": "succeeded",
            "created_at": "2026-09-29T08:00:00+00:00",
            "config": deepcopy(config),
            "periods": [
                {"trading_day": "2026-09-28", "equity": "1000"},
                {"trading_day": "2026-09-29", "equity": value},
            ],
        }
    c.market_data.upsert_instruments([{"symbol": "000001", "name": "平安银行", "exchange": "SZSE"}])
    c.market_data.upsert_bars(
        [
            {
                "symbol": "000001",
                "trading_day": day,
                "available_at": at,
                "open": price,
                "close": price,
                "high": price,
                "low": price,
                "volume": "1",
            }
            for day, at, price in (
                ("2026-09-28", "2026-09-28T15:00:00+08:00", "10"),
                ("2026-09-29", "2026-09-29T15:00:00+08:00", "12"),
            )
        ]
    )
    return c


def test_market_and_backtest_comparison_decimal_normalization_without_mutation():
    c = setup()
    before = deepcopy(c.backtests.rows)
    result = comparison_series(c, "backtest", "main", "u", symbol="000001")
    assert result["points"][0] == {"day": "2026-09-28", "amount": "1000", "return_rate": "0"}
    assert Decimal(result["points"][1]["amount"]) == 1200
    assert Decimal(result["points"][1]["return_rate"]) == Decimal(".2")
    other = comparison_series(c, "backtest", "main", "u", other_run_id="other")
    assert other["points"][1]["amount"] == "1100"
    assert [row["id"] for row in comparison_candidates(c, "main", "u", "")] == ["other"]
    assert c.backtests.rows == before
    assert search_instruments(c, "平安")[0]["id"] == "000001"
    assert search_instruments(c, "上证指数")[0]["id"] == "sh000001"


@pytest.mark.parametrize(
    "change",
    [
        {"start_day": "2026-09-27"},
        {"end_day": "2026-09-28"},
        {"initial_cash": "2000"},
        {"initial_positions": {"000001": "100"}},
    ],
)
def test_incompatible_backtest_is_excluded_and_rejected(change):
    c = setup()
    c.backtests.rows["other"]["config"].update(change)
    assert comparison_candidates(c, "main", "u", "") == []
    with pytest.raises(StateConflictError):
        comparison_series(c, "backtest", "main", "u", other_run_id="other")


def test_comparison_permissions_and_ambiguous_request():
    c = setup()
    with pytest.raises(NotFoundError):
        comparison_series(c, "backtest", "main", "other", symbol="000001")
    with pytest.raises(NotFoundError):
        comparison_series(c, "backtest", "main", "u", other_run_id="private")
    with pytest.raises(ValidationError):
        comparison_series(c, "backtest", "main", "u", symbol="000001", other_run_id="other")
    with pytest.raises(ValidationError):
        comparison_series(c, "live", "l", "u", other_run_id="other")


def test_future_quote_cannot_change_comparison_or_supply_missing_baseline():
    c = setup()
    c.market_data.daily_bars["000001", "2026-09-29"]["available_at"] = "2026-09-30T15:00:00+08:00"
    result = comparison_series(c, "backtest", "main", "u", symbol="000001")
    assert Decimal(result["points"][1]["amount"]) == 1000
    c.market_data.daily_bars.clear()
    with pytest.raises(StateConflictError, match="真实行情"):
        comparison_series(c, "backtest", "main", "u", symbol="000001")


def test_live_comparison_uses_same_profit_scale_and_has_no_backtest_sources():
    c = setup()
    c.state.live_instances["l"]["started_at"] = "2026-09-28T08:00:00+00:00"
    result = comparison_series(c, "live", "l", "u", symbol="000001")
    assert Decimal(result["points"][0]["amount"]) == 0
    assert Decimal(result["points"][-1]["amount"]) == 200


def test_candidates_use_names_without_dates_and_limit_to_twenty():
    c = setup()
    for index in range(30):
        original = c.backtests.get("other")
        assert original is not None
        c.backtests.save(
            {
                **original,
                "id": f"candidate-{index}",
                "name": "匹配名称" + str(index),
                "created_at": "2026-10-24T01:00:00Z",
            },
            b"[]",
        )
    rows = comparison_candidates(c, "main", "u", "匹配名称")
    assert len(rows) == 20
    assert all(row["name"].startswith("匹配名称") and "2026-" not in row["name"] for row in rows)

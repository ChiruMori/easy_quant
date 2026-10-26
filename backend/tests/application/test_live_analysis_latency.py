from datetime import timedelta
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

from easy_quant.api.blueprints.strategies import GRID_TEMPLATE
from easy_quant.application.services.live_runtime import analyze_live_instance
from tests.application.test_live_strategy_state import prepare


def test_grid_quotes_without_reading_any_market_history(fixed_now, caplog):
    container = prepare(fixed_now, GRID_TEMPLATE)
    container.state.live_instances["l"]["parameters"] = {"symbol": "688836"}
    calls = []

    def quotes(symbols, *, force):
        assert force
        calls.append(symbols)
        return {symbol: "10" for symbol in symbols}

    container.data_sync = cast(Any, SimpleNamespace(quotes=quotes))
    with (
        patch.object(container.market_data, "list_runtime_bars", side_effect=AssertionError),
        patch.object(container.state.strategies, "versions", side_effect=AssertionError),
        caplog.at_level("INFO"),
    ):
        result = analyze_live_instance(container, "l", "on_market", fixed_now)
    assert calls == [["688836"]]
    assert result["created"]
    assert "rows=0" in caplog.text and "quote_only=True" in caplog.text
    assert "completed=save_results" in caplog.text
    assert "quotes" in cast(dict, result["timings"])


def test_universe_only_strategy_reads_recent_day_instead_of_default_year(fixed_now):
    container = prepare(
        fixed_now,
        "def on_market(c,p):\n print(c.universe())\n return []",
    )
    today = fixed_now.date()
    container.market_data.list_trading_days = lambda: [
        today - timedelta(days=offset) for offset in range(500)
    ]
    with patch.object(container.market_data, "list_runtime_bars", return_value=[]) as read:
        analyze_live_instance(container, "l", "on_market", fixed_now)
    assert read.call_args.args == (today - timedelta(days=1), today)


def test_quote_only_portfolio_marks_other_holdings_in_one_batch(fixed_now):
    from decimal import Decimal

    from easy_quant.application.services.recommendation_actions import (
        ActionCommand,
        RecommendationActionService,
    )
    from easy_quant.domain.live_tracking.ledger import OperationKind
    from tests.fakes.core import SequentialIdGenerator
    from tests.fakes.live_tracking import seed_recommendation

    container = prepare(fixed_now, GRID_TEMPLATE)
    actions = RecommendationActionService(
        container.live_tracking, container.authentication.clock, SequentialIdGenerator()
    )
    for index, symbol in enumerate(["000001", "000002"]):
        row = seed_recommendation(container, f"r-{index}")
        row["instrument_id"] = symbol
        actions.apply(
            row["id"],
            "u",
            ActionCommand(
                OperationKind.CORRECT,
                f"buy-{index}",
                0,
                symbol=symbol,
                action="buy",
                quantity=Decimal(100),
                price=Decimal(10),
                fee=Decimal(0),
            ),
        )
    requests = []

    def quotes(symbols, *, force):
        requests.append(symbols)
        return {symbol: "10" for symbol in symbols}

    container.data_sync = cast(Any, SimpleNamespace(quotes=quotes))
    with patch.object(container.market_data, "list_runtime_bars", side_effect=AssertionError):
        analyze_live_instance(container, "l", "on_market", fixed_now)
    assert requests == [["000001", "000002"]]

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from easy_quant.application.services import live_runtime
from easy_quant.application.services.live_reporting import operation_page, portfolio_summary
from easy_quant.application.services.manual_operations import ManualCommand, ManualOperationService
from easy_quant.application.services.recommendation_actions import (
    ActionCommand,
    RecommendationActionService,
    actual_portfolio,
)
from easy_quant.domain.live_tracking.ledger import OperationKind
from easy_quant.domain.live_tracking.reservations import reservations
from easy_quant.domain.shared.errors import NotFoundError, StateConflictError
from easy_quant.domain.strategies.entities import (
    Signal,
    StrategyDefinition,
    StrategyRun,
    StrategyRunStatus,
    StrategyVersion,
)
from easy_quant.strategy_api.context import RuntimeContext
from tests.fakes.core import SequentialIdGenerator
from tests.fakes.live_tracking import action_container, seed_recommendation


def manual(container):
    return ManualOperationService(
        container.live_tracking, container.authentication.clock, SequentialIdGenerator()
    )


def test_library_subposition_budget_holding_limit_and_cross_round_locks():
    context = RuntimeContext(
        {
            "cash": "1000000",
            "reserved_cash": "200000",
            "pending_buy_symbols": ["old"],
            "positions": {},
            "fee_rate": "0",
        }
    )
    signals = [
        context.signal(str(index), "buy", ".1", "candidate", price="10", expected_holdings=10)
        for index in range(50)
    ]
    assert sum(Decimal(str(row["quantity"])) > 0 for row in signals) == 9
    assert signals[0]["ratio_basis"] == Decimal(100000)
    assert signals[0]["quantity"] == 1000
    assert context.portfolio()["available_cash"] == 710000
    assert context.signal("old", "buy", ".1", "pending", price=10)["quantity"] == 0
    sell = RuntimeContext({"positions": {"x": "1000"}, "reserved_positions": {"x": "800"}})
    assert sell.signal("x", "sell", "1", "locked")["quantity"] == 0


def test_platform_reserves_raw_signals_atomically_and_passes_locks_to_next_round(
    monkeypatch, fixed_now
):
    c = action_container(cash=Decimal(10000))
    c.state.recommendations["l"] = []
    c.state.strategies.add_definition(StrategyDefinition("s", "u", "test"))
    c.state.strategies.add_version(
        StrategyVersion("v", "s", 1, "def before_market(c,p):\n return []", "hash", fixed_now)
    )
    seen = []

    class Runner:
        def __init__(self, *_args):
            pass

        def run(self, _version, _parameters, context, *, phase):
            seen.append(context)
            return StrategyRun(
                "run",
                "v",
                StrategyRunStatus.SUCCEEDED,
                {},
                [
                    Signal(f"{index:06}", "buy", Decimal(100), "raw", reference_price=Decimal(10))
                    for index in range(30)
                ],
            )

    monkeypatch.setattr(live_runtime, "SubprocessStrategyRunner", Runner)
    first = live_runtime.analyze_live_instance(c, "l", "before_market", fixed_now)
    assert isinstance(first["created"], list)
    assert len(first["created"]) == 9
    second = live_runtime.analyze_live_instance(
        c, "l", "before_market", fixed_now + timedelta(days=1)
    )
    assert second["created"] == []
    assert Decimal(seen[1]["reserved_cash"]) == Decimal("9002.7")
    assert len(seen[1]["pending_buy_symbols"]) == 9
    assert seen[1]["positions"] == {} and c.state.portfolio_ledger == []


def test_correction_protects_other_reservation_and_reject_releases():
    c = action_container(cash=Decimal(2000))
    c.state.recommendations["l"][0]["quantity"] = "100"
    seed_recommendation(c, "second", quantity="100", price="10")
    actions = RecommendationActionService(
        c.live_tracking, c.authentication.clock, SequentialIdGenerator()
    )
    with pytest.raises(StateConflictError, match="锁定资金"):
        actions.apply(
            "r",
            "u",
            ActionCommand(
                OperationKind.CORRECT, "correct-key", 0, quantity=Decimal(200), price=Decimal(10)
            ),
        )
    assert not c.state.portfolio_ledger
    actions.apply("second", "u", ActionCommand(OperationKind.REJECT, "reject-key", 0))
    actions.apply(
        "r",
        "u",
        ActionCommand(
            OperationKind.CORRECT, "correct-key", 0, quantity=Decimal(200), price=Decimal(10)
        ),
    )
    with c.live_tracking.transaction() as state:
        assert reservations(state.recommendations["l"]).cash == 0
        assert actual_portfolio(state, "l").cash == 0


@pytest.mark.parametrize(
    "quantity,symbol,action", [("1", None, None), ("100", "other", None), ("100", None, "sell")]
)
def test_correction_rejects_non_lots_or_changed_identity(quantity, symbol, action):
    c = action_container()
    service = RecommendationActionService(
        c.live_tracking, c.authentication.clock, SequentialIdGenerator()
    )
    with pytest.raises(StateConflictError):
        service.apply(
            "r",
            "u",
            ActionCommand(
                OperationKind.CORRECT,
                "correct-key",
                0,
                symbol=symbol,
                action=action,
                quantity=Decimal(quantity),
                price=Decimal(1),
            ),
        )
    assert not c.state.operations


def test_manual_increase_confirmation_idempotency_and_reservation_protection():
    c = action_container()
    service = manual(c)
    command = ManualCommand(
        "manual-key", "000002", "buy", Decimal(100), Decimal(10), Decimal(".13")
    )
    preview = service.apply("l", "u", command, preview=True)
    assert preview["required_increase"] == "100.13"
    assert not c.state.operations
    with pytest.raises(StateConflictError, match="风险"):
        service.apply("l", "u", command)
    with pytest.raises(StateConflictError, match="追加"):
        service.apply("l", "u", replace(command, risk_acknowledged=True))
    command = replace(command, risk_acknowledged=True, confirmed_increase=Decimal("100.13"))
    response = service.apply("l", "u", command)
    assert service.apply("l", "u", command) == response
    assert len(c.state.portfolio_ledger) == 2
    assert len(c.state.audit_events) == len(c.state.operations) == 1
    assert c.state.live_instances["l"]["capital_added"] == "100.13"
    assert c.state.live_instances["l"]["cash"] == "100.00"
    with pytest.raises(StateConflictError, match="幂等"):
        service.apply("l", "u", replace(command, price=Decimal(11)))
    with pytest.raises(NotFoundError):
        service.apply("l", "other", command)


def test_manual_sale_protects_locked_positions():
    c = action_container()
    c.state.recommendations["l"] = []
    c.state.live_instances["l"]["initial_positions"] = {"000001": "200"}
    seed_recommendation(c, action="sell", quantity="200")
    with pytest.raises(StateConflictError, match="锁定持仓"):
        manual(c).apply(
            "l",
            "u",
            ManualCommand("manual-key", "000001", "sell", Decimal(100), Decimal(10), Decimal(0)),
            preview=True,
        )


def test_manual_commit_failure_rolls_back_funding_and_trade():
    c = action_container()
    original = c.live_tracking
    before = deepcopy(c.state)

    class BrokenStore:
        @contextmanager
        def transaction(self):
            with original.transaction() as state:
                yield state
                raise RuntimeError("fake commit failure")

    command = ManualCommand(
        "manual-key", "000002", "buy", Decimal(100), Decimal(10), Decimal(0), True, Decimal(100)
    )
    with pytest.raises(RuntimeError):
        ManualOperationService(
            BrokenStore(), c.authentication.clock, SequentialIdGenerator()
        ).apply("l", "u", command)
    assert c.state.live_instances == before.live_instances
    assert not c.state.portfolio_ledger and not c.state.operations


def test_pagination_search_and_equity_excludes_cash_injection():
    c = action_container()
    now = c.authentication.clock.now()
    c.state.live_instances["l"]["started_at"] = (now - timedelta(days=1)).isoformat()
    manual(c).apply(
        "l",
        "u",
        ManualCommand(
            "manual-key",
            "000002",
            "buy",
            Decimal(100),
            Decimal(10),
            Decimal(".13"),
            True,
            Decimal("100.13"),
        ),
    )
    c.market_data.upsert_bars(
        [
            {
                "symbol": "000002",
                "trading_day": now.date().isoformat(),
                "open": "12",
                "high": "12",
                "low": "12",
                "close": "12",
                "volume": "1",
                "available_at": now.isoformat(),
            }
        ]
    )
    with c.live_tracking.transaction() as state:
        summary = portfolio_summary(state, "l", c.market_data, now)
        assert summary["profit"] == "199.87"
        assert summary["reserved_cash"] == "100"
        assert summary["available_cash"] == "0"
        page = operation_page(state, "l", 99, 1, operation_type="manual_buy")
        assert page["page"] == 1 and page["total"] == 1
        assert page["items"][0]["status"] == "executed"
        assert operation_page(state, "l", 1, 1, status="pending")["total"] == 1
    c.market_data.daily_bars.clear()
    with c.live_tracking.transaction() as state:
        summary = portfolio_summary(state, "l", c.market_data, now)
        assert summary["profit"] is None and summary["missing_symbols"] == ["000002"]


def test_initial_position_baseline_and_future_prices_are_time_consistent():
    c = action_container()
    now = c.authentication.clock.now()
    started = now - timedelta(days=1)
    c.state.live_instances["l"].update(
        started_at=started.isoformat(), initial_positions={"000002": "200"}
    )

    def bar(at, price):
        return {
            "symbol": "000002",
            "trading_day": at.date().isoformat(),
            "available_at": at.isoformat(),
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "volume": "1",
        }

    c.market_data.upsert_bars(
        [
            bar(started - timedelta(days=1), "10"),
            bar(now, "12"),
            bar(now + timedelta(days=1), "100"),
        ]
    )
    with c.live_tracking.transaction() as state:
        summary = portfolio_summary(state, "l", c.market_data, now)
        assert summary["profit"] == "400"
        assert summary["capital_pool"] == "1000"
        assert summary["curve"][0]["profit"] == "0"
    c.market_data.daily_bars.clear()
    c.market_data.upsert_bars([bar(now, "12")])
    with c.live_tracking.transaction() as state:
        summary = portfolio_summary(state, "l", c.market_data, now)
        assert summary["profit"] is None and summary["missing_symbols"] == ["000002"]

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal

import pytest

from easy_quant.application.services.recommendation_actions import (
    ActionCommand,
    RecommendationActionService,
    actual_portfolio,
)
from easy_quant.domain.live_tracking.ledger import OperationKind
from easy_quant.domain.shared.errors import NotFoundError, StateConflictError
from tests.fakes.core import SequentialIdGenerator
from tests.fakes.live_tracking import action_container, seed_live, seed_recommendation


def service(container):
    return RecommendationActionService(
        container.live_tracking, container.authentication.clock, SequentialIdGenerator()
    )


def command(kind=OperationKind.CONFIRM, key="request-key", **kwargs):
    return ActionCommand(kind, key, 0, **kwargs)


def snapshot(container):
    return deepcopy(
        (
            container.state.live_instances,
            container.state.recommendations,
            container.state.operations,
            container.state.portfolio_ledger,
            container.state.audit_events,
        )
    )


def test_ten_repeats_return_identical_response_and_one_ledger_entry():
    container = action_container()
    actions = service(container)
    responses = [actions.apply("r", "u", command(fee=Decimal("0.13"))) for _ in range(10)]
    assert all(row == responses[0] for row in responses)
    assert (
        len(container.state.operations)
        == len(container.state.portfolio_ledger)
        == len(container.state.audit_events)
        == 1
    )
    with container.live_tracking.transaction() as state:
        portfolio = actual_portfolio(state, "l")
        assert portfolio.cash == Decimal("899.87")
        assert portfolio.positions == {"000001": Decimal(10)}
        assert portfolio.costs == {"000001": Decimal(10)}
    operation = next(iter(container.state.operations.values()))
    assert operation["fee"] == "0.13" and operation["quantity"] == "10"
    assert container.state.audit_events[0]["after_summary"]["version"] == 1


@pytest.mark.parametrize("kind", [OperationKind.CONFIRM, OperationKind.CORRECT])
def test_insufficient_cash_does_not_write_or_consume_key(kind):
    container = action_container(cash=Decimal(10))
    before = snapshot(container)
    actions = service(container)
    values = {"symbol": "000001", "action": "buy", "quantity": Decimal(10), "price": Decimal(10)}
    with pytest.raises(StateConflictError, match="负现金"):
        actions.apply("r", "u", command(kind, **values))
    assert snapshot(container) == before
    actions.apply(
        "r",
        "u",
        command(
            OperationKind.CORRECT,
            symbol="000001",
            action="buy",
            quantity=Decimal(1),
            price=Decimal(10),
        ),
    )
    assert len(container.state.portfolio_ledger) == 1


def test_overselling_does_not_write_and_reject_has_no_ledger():
    container = action_container()
    before = snapshot(container)
    actions = service(container)
    with pytest.raises(StateConflictError, match="负持仓"):
        actions.apply(
            "r",
            "u",
            command(
                OperationKind.CORRECT,
                symbol="000001",
                action="sell",
                quantity=Decimal(1),
                price=Decimal(10),
            ),
        )
    assert snapshot(container) == before
    actions.apply("r", "u", command(OperationKind.REJECT))
    assert container.state.portfolio_ledger == []
    assert container.state.recommendations["l"][0]["status"] == "rejected"


@pytest.mark.parametrize(
    "changed",
    [
        {"kind": OperationKind.REJECT},
        {"price": Decimal(11)},
        {"fee": Decimal(1)},
        {"expected_version": 1},
        {"symbol": "000002"},
    ],
)
def test_key_cannot_be_reused_for_a_different_command(changed):
    container = action_container()
    actions = service(container)
    first = command(price=Decimal(10))
    actions.apply("r", "u", first)
    before = snapshot(container)
    with pytest.raises(StateConflictError, match="幂等键"):
        actions.apply("r", "u", replace(first, **changed))
    seed_recommendation(container, "r2")
    with pytest.raises(StateConflictError, match="幂等键"):
        actions.apply("r2", "u", first)
    assert snapshot(container)[2:] == before[2:]


def test_request_identity_keeps_decimal_precision_and_equivalent_zeroes():
    container = action_container()
    actions = service(container)
    first = actions.apply("r", "u", command(price=Decimal("10.00")))
    assert actions.apply("r", "u", command(price=Decimal("10"))) == first
    large = command(price=Decimal("123456789012345678901234567890.01"))
    assert large.fingerprint("r") != replace(
        large, price=Decimal("123456789012345678901234567890.02")
    ).fingerprint("r")


def test_owner_is_rechecked_and_keys_are_isolated_by_user():
    container = action_container()
    actions = service(container)
    with pytest.raises(NotFoundError):
        actions.apply("r", "other", command())
    seed_live(container, "other", "other-live")
    seed_recommendation(container, "other-r", "other", "other-live")
    assert (
        actions.apply("r", "u", command())["id"]
        != actions.apply("other-r", "other", command())["id"]
    )
    assert len(container.state.operations) == 2


@pytest.mark.parametrize("same_recommendation", [True, False])
def test_concurrent_commands_validate_against_latest_committed_ledger(same_recommendation):
    container = action_container(cash=Decimal(100))
    seed_recommendation(container, "r2")
    actions = service(container)

    def apply(index):
        try:
            return actions.apply(
                "r" if same_recommendation or index == 0 else "r2",
                "u",
                command(key=f"request-{index}"),
            )
        except StateConflictError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(apply, [0, 1]))
    assert sum(result is not None for result in results) == 1
    assert len(container.state.portfolio_ledger) == len(container.state.operations) == 1
    assert container.state.live_instances["l"]["cash"] == "0"


@pytest.mark.parametrize("stage", ["ledger", "audit", "commit"])
def test_storage_failure_rolls_back_all_state_and_retry_succeeds(stage):
    container = action_container()
    original = container.live_tracking
    before = snapshot(container)

    class BrokenList(list):
        def append(self, _value):
            raise RuntimeError("fake write failure")

    class BrokenStore:
        @contextmanager
        def transaction(self):
            with original.transaction() as state:
                if stage != "commit":
                    setattr(state, stage, BrokenList())
                yield state
                if stage == "commit":
                    raise RuntimeError("fake commit failure")

    actions = RecommendationActionService(
        BrokenStore(), container.authentication.clock, SequentialIdGenerator()
    )
    with pytest.raises(RuntimeError, match="fake"):
        actions.apply("r", "u", command())
    assert snapshot(container) == before
    service(container).apply("r", "u", command())
    assert len(container.state.operations) == 1


def test_same_timestamp_and_reversed_ids_keep_posting_order():
    container = action_container()
    actions = service(container)
    actions.apply("r", "u", command())
    seed_recommendation(container, "sale", action="sell", quantity="5", price="11.25")
    actions.apply("sale", "u", command(key="sell-key-1", fee=Decimal("0.01")))
    # JSON lists order by UUID key rather than transaction order in the SQL adapter.
    container.state.portfolio_ledger.reverse()
    with container.live_tracking.transaction() as state:
        portfolio = actual_portfolio(state, "l")
        assert portfolio.cash == Decimal("956.24")
        assert portfolio.positions["000001"] == 5
        assert portfolio.costs["000001"] == 10

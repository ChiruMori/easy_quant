from decimal import Decimal

import pytest

from easy_quant.application.services import live_runtime
from easy_quant.application.services.recommendation_actions import (
    ActionCommand,
    RecommendationActionService,
)
from easy_quant.domain.live_tracking.ledger import OperationKind
from easy_quant.domain.shared.errors import StateConflictError
from easy_quant.domain.strategies.entities import (
    Signal,
    StrategyDefinition,
    StrategyRun,
    StrategyRunStatus,
    StrategyVersion,
)
from tests.fakes.core import SequentialIdGenerator
from tests.fakes.live_tracking import action_container


def setup(container, fixed_now):
    definition = StrategyDefinition("s", "u", "test", current_version_id="v")
    version = StrategyVersion(
        "v", "s", 1, "def before_market(context, parameters):\n return []", "hash", fixed_now
    )
    container.state.strategies.add_definition(definition)
    container.state.strategies.add_version(version)


def test_live_analysis_rebuilds_portfolio_and_does_not_overwrite_concurrent_confirmation(
    monkeypatch, fixed_now
):
    container = action_container()
    setup(container, fixed_now)
    actions = RecommendationActionService(
        container.live_tracking, container.authentication.clock, SequentialIdGenerator()
    )
    actions.apply("r", "u", ActionCommand(OperationKind.CONFIRM, "first-key", 0))
    container.state.live_instances["l"]["positions"] = {"000001": "999"}
    # A second analysis after confirmation must use the ledger rather than this corrupted cache.
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
                [Signal("000002", "buy", Decimal(1), "new")],
            )

    monkeypatch.setattr(live_runtime, "SubprocessStrategyRunner", Runner)
    result = live_runtime.analyze_live_instance(container, "l", "before_market", fixed_now)
    assert seen[0]["positions"] == {"000001": "10"}
    assert seen[0]["cash"] == "900" and seen[0]["costs"] == {"000001": "10"}
    assert container.state.recommendations["l"][0]["status"] == "confirmed"
    assert result["created"] == [container.state.recommendations["l"][-1]]
    repeated = live_runtime.analyze_live_instance(container, "l", "before_market", fixed_now)
    assert repeated["created"] == []
    assert len(container.state.recommendations["l"]) == 2


def test_pause_during_strategy_execution_prevents_saving_new_recommendations(
    monkeypatch, fixed_now
):
    container = action_container()
    setup(container, fixed_now)

    class Runner:
        def __init__(self, *_args):
            pass

        def run(self, _version, _parameters, _context, *, phase):
            with container.live_tracking.transaction() as state:
                state.instances["l"] = {**state.instances["l"], "status": "paused"}
            return StrategyRun(
                "run",
                "v",
                StrategyRunStatus.SUCCEEDED,
                {},
                [Signal("000001", "buy", Decimal(1), "new")],
            )

    monkeypatch.setattr(live_runtime, "SubprocessStrategyRunner", Runner)
    with pytest.raises(StateConflictError, match="暂停"):
        live_runtime.analyze_live_instance(container, "l", "before_market", fixed_now)
    assert len(container.state.recommendations["l"]) == 1
    assert container.state.audit_events == [] and container.state.deliveries == []


def test_confirmation_during_analysis_is_preserved_by_fresh_transaction(monkeypatch, fixed_now):
    container = action_container()
    setup(container, fixed_now)
    actions = RecommendationActionService(
        container.live_tracking, container.authentication.clock, SequentialIdGenerator()
    )

    class Runner:
        def __init__(self, *_args):
            pass

        def run(self, _version, _parameters, _context, *, phase):
            actions.apply("r", "u", ActionCommand(OperationKind.CONFIRM, "concurrent-key", 0))
            return StrategyRun(
                "run",
                "v",
                StrategyRunStatus.SUCCEEDED,
                {},
                [Signal("000002", "buy", Decimal(1), "new")],
            )

    monkeypatch.setattr(live_runtime, "SubprocessStrategyRunner", Runner)
    live_runtime.analyze_live_instance(container, "l", "before_market", fixed_now)
    assert container.state.recommendations["l"][0]["status"] == "confirmed"
    assert container.state.recommendations["l"][0]["version"] == 1
    assert container.state.live_instances["l"]["positions"] == {"000001": "10"}
    assert len(container.state.portfolio_ledger) == 1

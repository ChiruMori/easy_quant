from decimal import Decimal
from typing import Any, cast

import pytest

from easy_quant.application.services.live_runtime import analyze_live_instance
from easy_quant.application.services.recommendation_actions import (
    ActionCommand,
    RecommendationActionService,
)
from easy_quant.domain.live_tracking.ledger import OperationKind
from easy_quant.domain.shared.errors import StateConflictError
from easy_quant.domain.strategies.entities import StrategyDefinition, StrategyVersion
from tests.fakes.core import SequentialIdGenerator
from tests.fakes.live_tracking import action_container


def prepare(fixed_now, source):
    container = action_container()
    container.state.strategies.add_definition(StrategyDefinition("s", "u", "通用测试"))
    container.state.strategies.add_version(StrategyVersion("v", "s", 1, source, "h", fixed_now))
    return container


def test_state_survives_phases_and_retries_but_portfolio_waits_for_actual_trade(fixed_now):
    source = """def before_market(c,p):
    c.store.set('count', c.store.get('count', 0) + 1)
    return [c.signal('000001', 'buy', '0.1', '建立部分仓位', price='10', lot_size=1)]
def on_market(c,p):
    print(c.store.get('count'), c.position('000001'))
    c.quotes(list(c.portfolio()['positions']))
    return [c.signal('000001', 'sell', '0.5', '减少一半仓位', lot_size=1)]
def after_market(c,p):
    return []
"""
    container = prepare(fixed_now, source)
    before = analyze_live_instance(container, "l", "before_market", fixed_now)
    recommendation = cast(list[dict[str, Any]], before["created"])[0]
    assert recommendation["ratio"] == "0.1"
    assert recommendation["suggested_price"] == "10"
    assert container.state.live_instances["l"]["strategy_state"] == {"count": 1}
    assert container.state.portfolio_ledger == []
    assert analyze_live_instance(container, "l", "before_market", fixed_now)["created"] == []
    assert container.state.live_instances["l"]["strategy_state"] == {"count": 1}
    RecommendationActionService(
        container.live_tracking, container.authentication.clock, SequentialIdGenerator()
    ).apply(
        recommendation["id"],
        "u",
        ActionCommand(
            OperationKind.CORRECT,
            "actual-buy",
            0,
            symbol="000001",
            action="buy",
            quantity=Decimal(5),
            price=Decimal(10),
            fee=Decimal(0),
        ),
    )
    result = analyze_live_instance(container, "l", "on_market", fixed_now, {"000001": "12"})
    assert result["stdout"] == "1 5\n"
    assert cast(list[dict[str, Any]], result["created"])[0]["quantity"] == "2"
    assert container.state.live_instances["l"]["positions"] == {"000001": "5"}
    assert (
        analyze_live_instance(container, "l", "on_market", fixed_now, {"000001": "12"})["created"]
        == []
    )


def test_failed_phase_does_not_commit_kv_or_consume_stage_key(fixed_now):
    container = prepare(fixed_now, "def before_market(c,p):\n c.store.set('x', 1)\n return 1/0")
    with pytest.raises(StateConflictError, match="运行失败"):
        analyze_live_instance(container, "l", "before_market", fixed_now)
    assert "strategy_state" not in container.state.live_instances["l"]
    assert "completed_phases" not in container.state.live_instances["l"]


def test_notification_failure_recovers_without_reexecuting_strategy(fixed_now, monkeypatch):
    container = prepare(
        fixed_now,
        "def before_market(c,p):\n c.store.set('n', c.store.get('n',0)+1)\n"
        " return [c.signal('000001','buy','0.1','test',price='10',lot_size=1)]",
    )
    delivered = []

    def fail(*args):
        raise RuntimeError("temporary notification failure")

    monkeypatch.setattr("easy_quant.application.services.live_runtime.notify_owner", fail)
    with pytest.raises(RuntimeError, match="temporary"):
        analyze_live_instance(container, "l", "before_market", fixed_now)
    instance = container.state.live_instances["l"]
    assert instance["strategy_state"] == {"n": 1}
    assert instance["notification_outbox"]
    monkeypatch.setattr(
        "easy_quant.application.services.live_runtime.notify_owner",
        lambda *args: delivered.append(args[2]),
    )
    result = analyze_live_instance(container, "l", "before_market", fixed_now)
    assert result["created"] == []
    assert len(delivered) == 1
    assert container.state.live_instances["l"]["notification_outbox"] == {}
    assert container.state.live_instances["l"]["strategy_state"] == {"n": 1}

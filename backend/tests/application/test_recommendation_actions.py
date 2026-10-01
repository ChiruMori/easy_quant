from decimal import Decimal

import pytest

from easy_quant.application.services.recommendation_actions import RecommendationActionService
from easy_quant.domain.live_tracking.entities import Recommendation, RecommendationStatus
from easy_quant.domain.live_tracking.ledger import OperationKind, rebuild_portfolio
from easy_quant.domain.shared.errors import StateConflictError
from tests.fakes.core import SequentialIdGenerator


def recommendation(fixed_now):
    return Recommendation(
        "r", "l", "u", "v", fixed_now, "000001", "s", "buy", "10", "reason", "key"
    )


def test_ten_repeats_are_idempotent_and_ledger_rebuilds(fixed_now) -> None:
    item, service = recommendation(fixed_now), RecommendationActionService(SequentialIdGenerator())
    operations = [
        service.apply(
            item,
            OperationKind.CORRECT,
            "request-key",
            0,
            fixed_now,
            symbol="000001",
            action="buy",
            quantity=Decimal(10),
            price=Decimal(10),
        )
        for _ in range(10)
    ]
    assert len({operation.id for operation in operations}) == 1 and len(service.ledger) == 1
    assert rebuild_portfolio(Decimal(1000), service.ledger).positions["000001"] == 10


def test_optimistic_concurrency_rejects_stale_action(fixed_now) -> None:
    item, service = recommendation(fixed_now), RecommendationActionService(SequentialIdGenerator())
    service.apply(item, OperationKind.REJECT, "first-key", 0, fixed_now)
    with pytest.raises(StateConflictError):
        service.apply(item, OperationKind.REJECT, "second-key", 0, fixed_now)
    assert item.status is RecommendationStatus.REJECTED

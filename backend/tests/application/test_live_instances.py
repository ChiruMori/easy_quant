import pytest

from easy_quant.application.services.live_instances import LiveInstanceService
from easy_quant.domain.live_tracking.entities import LiveStatus
from easy_quant.domain.shared.errors import StateConflictError
from tests.fakes.core import SequentialIdGenerator


def test_start_pause_and_terminate(fixed_now) -> None:
    service = LiveInstanceService(SequentialIdGenerator())
    item = service.start(
        "owner", {"id": "b", "status": "succeeded", "strategy_version_id": "v"}, fixed_now
    )
    assert item.status is LiveStatus.ACTIVE and item.next_decision_at == fixed_now
    service.pause(item.id)
    assert item.status is LiveStatus.PAUSED
    service.terminate(item.id)
    assert item.status is LiveStatus.TERMINATED


def test_failed_backtest_cannot_start(fixed_now) -> None:
    with pytest.raises(StateConflictError):
        LiveInstanceService(SequentialIdGenerator()).start(
            "owner", {"id": "b", "status": "failed", "strategy_version_id": "v"}, fixed_now
        )

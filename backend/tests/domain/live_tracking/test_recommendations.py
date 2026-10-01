from easy_quant.application.services.live_analysis import LiveAnalysisService
from easy_quant.domain.live_tracking.entities import LiveInstance, LiveStatus
from tests.fakes.core import SequentialIdGenerator


def test_repeated_schedule_creates_one_pending_recommendation(fixed_now) -> None:
    instance = LiveInstance(
        "live", "owner", "backtest", "version", LiveStatus.ACTIVE, fixed_now, {}
    )
    service = LiveAnalysisService(SequentialIdGenerator())
    first = service.create_recommendation(
        instance, fixed_now, "000001", "signal", "buy", "100", "reason"
    )
    second = service.create_recommendation(
        instance, fixed_now, "000001", "signal", "buy", "100", "reason"
    )
    assert first is second
    assert len(service.recommendations) == 1
    assert instance.next_decision_at == fixed_now

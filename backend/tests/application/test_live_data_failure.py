from typing import Any, cast

import pytest

from easy_quant.api.blueprints.strategies import GRID_TEMPLATE
from easy_quant.application.services.acquisition import (
    AcquisitionFailed,
    AcquisitionService,
    ExponentialRetry,
)
from easy_quant.application.services.live_runtime import analyze_live_instance
from easy_quant.application.services.market_data_sync import (
    MarketDataSyncService,
    validate_live_quote_response,
)
from easy_quant.application.services.notification_runtime import attempt_delivery
from tests.application.test_acquisition_service import MemoryCache, Source
from tests.application.test_live_strategy_state import prepare
from tests.fakes.core import FixedClock, VirtualSleeper


def setup(fixed_now):
    container = prepare(fixed_now, GRID_TEMPLATE)
    container.state.live_instances["l"].update(
        name="离线网格", subscription_ids=["mine", "foreign"]
    )
    assert container.secret_box is not None
    for key, owner in [("mine", "u"), ("foreign", "other")]:
        container.state.subscriptions.append(
            {
                "id": key,
                "owner_id": owner,
                "enabled": True,
                "channel": "ntfy",
                "destination_encrypted": container.secret_box.encrypt("offline-fixture"),
            }
        )
    service = AcquisitionService(
        [Source("tencent", failures=100), Source("eastmoney", failures=100)],
        MemoryCache(),
        FixedClock(fixed_now),
        VirtualSleeper(),
        ExponentialRetry(2),
        shuffle=lambda _: None,
        retry_by_round=True,
        validate=validate_live_quote_response,
    )
    container.data_sync = MarketDataSyncService({"live-quotes": service}, container.market_data)
    return container, service


def test_exhausted_sources_alert_selected_owner_once_and_leave_phase_retryable(fixed_now):
    container, service = setup(fixed_now)
    sent = []

    class Channel:
        def send(self, *args):
            sent.append(args)

    container.notification_channels["ntfy"] = Channel()
    with pytest.raises(AcquisitionFailed) as captured:
        analyze_live_instance(container, "l", "on_market", fixed_now)
    assert len(cast(list, captured.value.details["attempts"])) == 4
    instance = container.state.live_instances["l"]
    assert not instance.get("completed_phases") and not instance.get("strategy_state")
    assert container.state.recommendations["l"] == []
    assert container.state.portfolio_ledger == []
    assert len(container.state.deliveries) == 1
    delivery = container.state.deliveries[0]
    assert delivery["subscription_id"] == "mine" and delivery["live_instance_id"] == "l"
    assert "tencent" in delivery["body"] and "eastmoney" in delivery["body"]
    assert "RuntimeError" in delivery["body"]
    assert delivery["status"] == "pending"
    queued = [job for job in container.jobs.list_all() if job.job_type == "notification-delivery"]
    assert len(queued) == 1 and not sent
    attempt_delivery(container, delivery["id"])
    assert len(sent) == 1
    with pytest.raises(AcquisitionFailed):
        analyze_live_instance(container, "l", "on_market", fixed_now)
    assert len(container.state.deliveries) == 1 and len(sent) == 1
    # Recovery uses actual live quotes and can still commit the previously failed phase.
    service.sources.clear()
    service.sources.append(Source("tencent", payload=b'[{"code":"000001","price":"10"}]'))
    result = analyze_live_instance(container, "l", "on_market", fixed_now)
    assert result["created"]
    assert container.state.live_instances["l"]["completed_phases"]["on_market"] == "2026-09-29"


def test_alert_enqueue_failure_preserves_original_error_and_persistent_outbox(
    fixed_now, monkeypatch
):
    container, _ = setup(fixed_now)
    enqueue = container.jobs.enqueue

    def fail_enqueue(*args, **kwargs):
        raise RuntimeError("offline enqueue failure")

    monkeypatch.setattr(container.jobs, "enqueue", fail_enqueue)
    with pytest.raises(AcquisitionFailed):
        analyze_live_instance(container, "l", "on_market", fixed_now)
    assert container.state.live_instances["l"]["notification_outbox"]
    monkeypatch.setattr(container.jobs, "enqueue", enqueue)
    with pytest.raises(AcquisitionFailed):
        analyze_live_instance(container, "l", "on_market", fixed_now)
    assert container.state.live_instances["l"]["notification_outbox"] == {}
    assert len(cast(Any, container.jobs).list_all()) == 1

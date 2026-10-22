import logging
from contextlib import suppress

from easy_quant.application.ports.notifications import (
    PermanentDeliveryError,
    TemporaryDeliveryError,
)
from easy_quant.application.services.notification_runtime import attempt_delivery, notify_owner
from tests.fakes.live_tracking import action_container


def setup():
    c = action_container()
    assert c.secret_box is not None
    c.state.subscriptions.append(
        {
            "id": "n",
            "owner_id": "u",
            "channel": "ntfy",
            "enabled": True,
            "destination_encrypted": c.secret_box.encrypt("hidden-topic-fixture"),
        }
    )
    return c


def test_record_precedes_external_send_and_duplicate_event_is_not_sent_twice():
    c = setup()
    calls = []

    class Channel:
        def send(self, *_args):
            assert c.state.deliveries[0]["status"] == "sending"
            assert c.state.deliveries[0]["attempts"] == 1
            calls.append(_args[-1])

    c.notification_channels["ntfy"] = Channel()
    first = notify_owner(c, "u", "l:day:phase", "title", "body", ["n"], "l")
    assert notify_owner(c, "u", "l:day:phase", "title", "body", ["n"], "l") == first
    assert len(calls) == 1
    assert first[0]["created_at"] and first[0]["delivered_at"]
    assert len(c.jobs.list_all()) == 1  # 延迟恢复任务在已成功投递时只做幂等检查。


def test_temporary_failure_recovery_and_redacted_errors(caplog):
    c = setup()
    calls = []

    class Channel:
        def send(self, *_args):
            calls.append(_args[-1])
            if len(calls) == 1:
                raise TemporaryDeliveryError("hidden-topic-fixture")

    c.notification_channels["ntfy"] = Channel()
    with caplog.at_level(logging.INFO):
        first = notify_owner(c, "u", "event", "title", "body", ["n"], "l")[0]
        assert first["status"] == "retry" and first["attempts"] == 1
        result = attempt_delivery(c, str(first["id"]), recover=True)
    assert result["status"] == "delivered" and result["attempts"] == 2
    assert calls[0] == calls[1]
    assert "hidden-topic-fixture" not in str(c.state.deliveries) + caplog.text


def test_crash_leaves_durable_sending_record_and_recovers_with_same_key():
    c = setup()

    class Crash(BaseException):
        pass

    class Channel:
        def send(self, *_args):
            raise Crash()

    c.notification_channels["ntfy"] = Channel()
    with suppress(Crash):
        notify_owner(c, "u", "event", "title", "body", ["n"], "l")
    row = c.state.deliveries[0]
    assert row["status"] == "sending" and c.jobs.list_all()

    class Recovered:
        def send(self, *_args):
            assert _args[-1] == row["idempotency_key"]

    c.notification_channels["ntfy"] = Recovered()
    assert attempt_delivery(c, row["id"], recover=True)["status"] == "delivered"


def test_missing_channel_permanent_failure_and_retry_limit_are_persistent():
    c = setup()
    result = notify_owner(c, "u", "missing", "title", "body", ["unknown"], "l")[0]
    assert result["status"] == "skipped" and result["error_code"] == "no_enabled_channel"

    class Permanent:
        def send(self, *_args):
            raise PermanentDeliveryError("hidden-topic-fixture")

    c.notification_channels["ntfy"] = Permanent()
    result = notify_owner(c, "u", "permanent", "title", "body", ["n"], "l")[0]
    assert result["status"] == "failed"
    assert "hidden-topic-fixture" not in str(c.state.deliveries)

    class Temporary:
        def send(self, *_args):
            raise TemporaryDeliveryError("fixture")

    c.notification_channels["ntfy"] = Temporary()
    result = notify_owner(c, "u", "retry", "title", "body", ["n"], "l")[0]
    for _ in range(3):
        result = attempt_delivery(c, str(result["id"]), recover=True)
    assert result["status"] == "failed" and result["error_code"] == "retry_exhausted"
    assert result["attempts"] == 3


def test_live_multiple_signals_generate_one_summary_per_channel(monkeypatch, fixed_now):
    from decimal import Decimal

    from easy_quant.application.services import live_runtime
    from easy_quant.domain.strategies.entities import (
        Signal,
        StrategyDefinition,
        StrategyRun,
        StrategyRunStatus,
        StrategyVersion,
    )

    c = setup()
    c.state.live_instances["l"]["initial_cash"] = "100000"
    c.state.live_instances["l"]["subscription_ids"] = ["n"]
    c.state.recommendations["l"] = []
    c.state.strategies.add_definition(StrategyDefinition("s", "u", "test"))
    c.state.strategies.add_version(
        StrategyVersion("v", "s", 1, "def before_market(c,p):\n return []", "hash", fixed_now)
    )

    class Runner:
        def __init__(self, *_args):
            pass

        def run(self, *_args, **_kwargs):
            return StrategyRun(
                "run",
                "v",
                StrategyRunStatus.SUCCEEDED,
                {},
                [
                    Signal(
                        f"{index:06}", "buy", Decimal(100), "reason", reference_price=Decimal(10)
                    )
                    for index in range(3)
                ],
            )

    calls = []

    class Channel:
        def send(self, *_args):
            calls.append(_args)

    c.notification_channels["ntfy"] = Channel()
    monkeypatch.setattr(live_runtime, "SubprocessStrategyRunner", Runner)
    first = live_runtime.analyze_live_instance(c, "l", "before_market", fixed_now)
    assert isinstance(first["created"], list) and len(first["created"]) == 3
    assert len(calls) == 1 and "本轮共 3 条" in calls[0][2]
    assert c.state.deliveries[0]["live_instance_id"] == "l"
    assert live_runtime.analyze_live_instance(c, "l", "before_market", fixed_now)["created"] == []
    assert len(calls) == 1 and len(c.state.deliveries) == 1

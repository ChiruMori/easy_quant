import logging

from easy_quant.application.services.live_schedules import reconcile_live_schedules
from easy_quant.domain.scheduling.entities import Job
from easy_quant.worker.handlers.live_tracking import register_live_handlers
from easy_quant.worker.registry import JobHandlerRegistry
from easy_quant.worker.runner import Worker
from tests.api.test_run_context import setup
from tests.api.test_schedule_control import setup as schedule_setup
from tests.fakes.core import VirtualSleeper


def test_system_can_delete_only_disabled_confirmed_plans_and_keeps_history():
    c, client, headers, item = schedule_setup()
    path = f"/api/v1/admin/schedules/{item['id']}"
    assert client.delete(path, headers=headers, json={"confirmed": True}).status_code == 409
    client.patch(path, headers=headers, json={"enabled": False})
    assert client.delete(path, headers=headers).status_code == 400
    assert item["id"] in c.state.schedules
    job = Job("history", "market-data-nightly", "history", {}, c.authentication.clock.now())
    c.jobs.enqueue(job)
    assert client.delete(path, headers=headers, json={"confirmed": True}).status_code == 200
    assert item["id"] not in c.state.schedules and c.jobs.get("history") is not None
    assert client.delete(path, headers=headers, json={"confirmed": True}).status_code == 404


def test_live_plans_are_private_automatic_and_removed_on_termination():
    c, client, headers, payload = setup()
    payload["after_market_enabled"] = True
    item = client.post("/api/v1/live-instances", json=payload, headers=headers).get_json()["data"]
    path = f"/api/v1/live-instances/{item['id']}"
    plans = client.get(path + "/schedules").get_json()["data"]
    assert len(plans) == 3 and all(row["enabled"] for row in plans)
    assert client.get("/api/v1/admin/schedules").get_json()["data"] == []
    for row in plans:
        base = f"/api/v1/admin/schedules/{row['id']}"
        assert client.patch(base, json={"enabled": False}, headers=headers).status_code == 409
        assert client.delete(base, json={"confirmed": True}, headers=headers).status_code == 409
        assert client.post(base + "/run", headers=headers).status_code == 409
    assert (
        client.post(
            "/api/v1/admin/schedules", headers=headers, json={"task_type": "live-analysis"}
        ).status_code
        == 400
    )
    assert client.post(path + "/pause", headers=headers).status_code == 200
    assert not any(row["enabled"] for row in client.get(path + "/schedules").get_json()["data"])
    assert client.post(path + "/resume", headers=headers).status_code == 200
    assert all(row["enabled"] for row in client.get(path + "/schedules").get_json()["data"])
    assert client.post(path + "/terminate", headers=headers).status_code == 200
    assert not c.state.schedules
    assert client.get(path + "/schedules").get_json()["data"] == []
    assert client.post(path + "/resume", headers=headers).status_code == 409
    c.state.live_instances[item["id"]]["owner_id"] = "other"
    assert client.get(path + "/schedules").status_code == 404


def test_old_live_plans_reconcile_before_enabled_filter_and_do_not_touch_system():
    c, client, headers, payload = setup()
    item = client.post("/api/v1/live-instances", json=payload, headers=headers).get_json()["data"]
    legacy = next(iter(c.state.schedules.values()))
    c.state.schedules["system"] = {
        "id": "system",
        "task_type": "market-data-nightly",
        "enabled": False,
    }
    c.state.schedules["orphan"] = {
        **legacy,
        "id": "orphan",
        "enabled": False,
        "configuration": {"instance_id": "deleted", "phase": "on_market"},
    }
    c.state.live_instances[item["id"]]["status"] = "paused"
    reconcile_live_schedules(c)
    assert "orphan" not in c.state.schedules
    assert not any(row["enabled"] for row in c.state.schedules.values())
    c.state.live_instances[item["id"]]["status"] = "terminated"
    reconcile_live_schedules(c)
    assert list(c.state.schedules) == ["system"]


def test_live_job_logs_and_failure_records_identify_the_source(monkeypatch, caplog):
    c, client, headers, payload = setup()
    item = client.post("/api/v1/live-instances", json=payload, headers=headers).get_json()["data"]
    registry = JobHandlerRegistry()
    register_live_handlers(registry, c)

    def fail(*_args):
        raise RuntimeError("离线策略故障")

    monkeypatch.setattr("easy_quant.worker.handlers.live_tracking.analyze_live_instance", fail)
    job = Job(
        "source-job",
        "live-analysis",
        "source-job",
        {"instance_id": item["id"], "phase": "before_market"},
        c.authentication.clock.now(),
    )
    c.jobs.enqueue(job)
    worker = Worker("fixture-worker", c.jobs, registry, c.authentication.clock, VirtualSleeper())
    with caplog.at_level(logging.INFO):
        assert worker.run_once()
    assert item["id"] in caplog.text and item["name"] in caplog.text
    saved = c.jobs.get(job.id)
    assert saved is not None
    assert saved.error_summary["live_instance_id"] == item["id"]
    result = client.get("/api/v1/admin/jobs").get_json()["data"]["items"][0]
    assert result["live_instance"] == {"id": item["id"], "name": item["name"]}

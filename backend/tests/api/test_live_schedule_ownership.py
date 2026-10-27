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


def test_live_plans_are_private_automatic_and_preserved_on_termination():
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
    retained = client.get(path + "/schedules").get_json()["data"]
    assert len(retained) == 3 and not any(row["enabled"] for row in retained)
    assert {row["id"] for row in retained} == {row["id"] for row in plans}
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
    assert "system" in c.state.schedules and len(c.state.schedules) == 3
    assert not any(row["enabled"] for row in c.state.schedules.values())


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


def test_only_paused_owner_can_edit_expression_atomically_and_resume_keeps_it():
    from copy import deepcopy

    c, client, headers, payload = setup()
    item = client.post("/api/v1/live-instances", json=payload, headers=headers).get_json()["data"]
    base = f"/api/v1/live-instances/{item['id']}"
    plans = client.get(base + "/schedules").get_json()["data"]
    plan = next(row for row in plans if row["configuration"]["phase"] == "on_market")
    path = base + "/schedules/" + plan["id"]
    update = {"schedule_expression": "30 10 * * 1-5"}
    assert client.patch(path, json=update, headers=headers).status_code == 409
    client.post(base + "/pause", headers=headers)
    before = deepcopy(c.state.schedules[plan["id"]])
    for invalid in ["bad", "60 10 * * 1-5", "0 10 31 2 *"]:
        assert (
            client.patch(path, json={"schedule_expression": invalid}, headers=headers).status_code
            == 400
        )
        assert c.state.schedules[plan["id"]] == before
    for invalid in [
        {**update, "enabled": True},
        {"configuration": {}},
        {"schedule_expression": None},
    ]:
        assert client.patch(path, json=invalid, headers=headers).status_code == 400
        assert c.state.schedules[plan["id"]] == before
    c.state.live_instances[item["id"]]["owner_id"] = "someone-else"
    assert client.patch(path, json=update, headers=headers).status_code == 404
    # The authenticated owner belongs to the original instance, independent of plan fields.
    c.state.live_instances[item["id"]]["owner_id"] = item["owner_id"]
    assert (
        client.patch(base + "/schedules/missing", json=update, headers=headers).status_code == 404
    )
    saved = client.patch(path, json=update, headers=headers)
    assert saved.status_code == 200
    assert not saved.get_json()["data"]["enabled"]
    assert saved.get_json()["data"]["custom_expression"]
    client.post(base + "/resume", headers=headers)
    assert c.state.schedules[plan["id"]]["schedule_expression"] == update["schedule_expression"]
    assert c.state.schedules[plan["id"]]["enabled"]
    client.post(base + "/terminate", headers=headers)
    reconcile_live_schedules(c)
    retained = c.state.schedules[plan["id"]]
    assert (
        retained["schedule_expression"] == update["schedule_expression"] and not retained["enabled"]
    )
    assert client.patch(path, json=update, headers=headers).status_code == 409


def test_new_instance_plans_do_not_reread_a_stale_request_snapshot():
    c, client, headers, payload = setup()

    class OldReadSnapshot(dict):
        def get(self, key, default=None):
            return default

    c.state.live_instances = OldReadSnapshot()
    response = client.post("/api/v1/live-instances", json=payload, headers=headers)
    assert response.status_code == 201
    identifier = response.get_json()["data"]["id"]
    assert len(c.state.schedules) == 2
    assert all(
        row["configuration"]["instance_id"] == identifier for row in c.state.schedules.values()
    )


def test_worker_repairs_instances_with_no_plans_idempotently():
    from easy_quant.application.services.live_schedules import reconcile_live_schedules

    c, client, headers, payload = setup()
    identifier = client.post("/api/v1/live-instances", json=payload, headers=headers).get_json()[
        "data"
    ]["id"]
    c.state.schedules.clear()
    reconcile_live_schedules(c)
    original = dict(c.state.schedules)
    assert len(original) == 2
    reconcile_live_schedules(c)
    assert c.state.schedules == original
    c.state.live_instances[identifier]["status"] = "paused"
    c.state.schedules.clear()
    reconcile_live_schedules(c)
    assert len(c.state.schedules) == 2 and not any(
        row["enabled"] for row in c.state.schedules.values()
    )
    c.state.live_instances[identifier]["status"] = "terminated"
    c.state.schedules.clear()
    reconcile_live_schedules(c)
    assert not c.state.schedules

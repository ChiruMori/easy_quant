from copy import deepcopy

from easy_quant.api.app import create_app
from tests.fakes.platform import make_test_container


def setup():
    container = make_test_container(initialize_admin=True)
    client = create_app(settings=container.settings, container=container).test_client()
    login = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "change-this-admin-password"}
    )
    headers = {"X-CSRF-Token": login.get_json()["data"]["csrf_token"]}
    response = client.post(
        "/api/v1/admin/schedules",
        headers=headers,
        json={
            "task_type": "market-data-nightly",
            "schedule_kind": "cron",
            "schedule_expression": "0 22 * * 1-5",
            "timezone": "Asia/Shanghai",
            "enabled": True,
        },
    )
    return container, client, headers, response.get_json()["data"]


def test_active_schedule_requires_disable_and_invalid_edit_is_atomic():
    container, client, headers, item = setup()
    url = f"/api/v1/admin/schedules/{item['id']}"
    assert (
        client.patch(url, headers=headers, json={"schedule_expression": "0 21 * * 1-5"}).status_code
        == 409
    )
    assert client.patch(url, headers=headers, json={"enabled": False}).status_code == 200
    before = deepcopy(container.state.schedules[item["id"]])
    assert (
        client.patch(url, headers=headers, json={"schedule_expression": "bad"}).status_code == 400
    )
    assert container.state.schedules[item["id"]] == before
    response = client.patch(
        url,
        headers=headers,
        json={"schedule_expression": "0 21 * * 1-5", "configuration": {"end_day": "2026-09-28"}},
    )
    assert response.status_code == 200
    changed = response.get_json()["data"]
    assert changed["next_run_at"] != item["next_run_at"]
    assert changed["enabled"] is False


def test_manual_execution_is_idempotent_and_preserves_disabled_schedule():
    container, client, headers, item = setup()
    base = f"/api/v1/admin/schedules/{item['id']}"
    client.patch(base, headers=headers, json={"enabled": False})
    before = deepcopy(container.state.schedules[item["id"]])
    assert client.post(base + "/run", headers=headers).status_code == 400
    headers["Idempotency-Key"] = "manual-1"
    first = client.post(base + "/run", headers=headers)
    second = client.post(base + "/run", headers=headers)
    assert first.status_code == 202
    assert first.get_json()["data"] == second.get_json()["data"]
    assert len(container.jobs.list_all()) == 1
    assert container.state.schedules[item["id"]] == before
    client.post("/api/v1/auth/logout", headers=headers)
    assert client.post(base + "/run", headers=headers).status_code == 401


def test_daily_update_manual_execution_uses_last_published_day():
    container, client, headers, item = setup()
    base = f"/api/v1/admin/schedules/{item['id']}"
    client.patch(base, headers=headers, json={"enabled": False})
    client.patch(
        base,
        headers=headers,
        json={"task_type": "market-data-acquisition", "configuration": {"mode": "daily-update"}},
    )
    headers["Idempotency-Key"] = "manual-2"
    response = client.post(base + "/run", headers=headers)
    job = container.jobs.get(response.get_json()["data"]["id"])
    assert job.payload["start_day"] == "2026-09-28"
    assert job.payload["end_day"] == "2026-09-28"
    assert job.payload["dataset_key"] == "daily-bars"

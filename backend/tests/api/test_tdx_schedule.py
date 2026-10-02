from easy_quant.api.app import create_app
from tests.fakes.platform import make_test_container


def test_tdx_schedule_requires_admin_and_persists_dedicated_task_type() -> None:
    container = make_test_container(initialize_admin=True)
    client = create_app(settings=container.settings, container=container).test_client()
    payload = {
        "task_type": "tdx-daily-update",
        "schedule_kind": "cron",
        "schedule_expression": "0 18,20 * * 1-5",
        "timezone": "Asia/Shanghai",
        "enabled": True,
    }
    assert client.post("/api/v1/admin/schedules", json=payload).status_code == 401
    login = client.post(
        "/api/v1/auth/login",
        json={
            "username": "admin",
            "password": container.settings.initial_admin_password.get_secret_value(),
        },
    )
    response = client.post(
        "/api/v1/admin/schedules",
        json=payload,
        headers={"X-CSRF-Token": login.get_json()["data"]["csrf_token"]},
    )
    assert response.status_code == 201
    item = response.get_json()["data"]
    assert item["configuration"] == {} and item["task_type"] == "tdx-daily-update"
    assert container.state.schedules[item["id"]]["timezone"] == "Asia/Shanghai"

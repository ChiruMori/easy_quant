from copy import deepcopy

from tests.api.test_run_context import setup


def test_light_detail_skips_valuation_and_delivery_scan(monkeypatch):
    container, client, headers, payload = setup()
    live = client.post("/api/v1/live-instances", json=payload, headers=headers).get_json()["data"]

    def slow(*_args):
        raise AssertionError("首屏不得运行慢估值")

    monkeypatch.setattr("easy_quant.application.services.live_reporting.portfolio_summary", slow)
    response = client.get(f"/api/v1/live-instances/{live['id']}?view=summary")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["balances"]["available_cash"] == "2000.25"
    assert data["operations"]["total"] == 0
    assert "portfolio" not in data and "notification_deliveries" not in data
    container.state.live_instances[live["id"]]["owner_id"] = "other"
    assert client.get(f"/api/v1/live-instances/{live['id']}/portfolio").status_code == 404


def test_live_delivery_pages_owner_scope_and_private_fields():
    container, client, headers, payload = setup()
    live = client.post("/api/v1/live-instances", json=payload, headers=headers).get_json()["data"]
    path = f"/api/v1/live-instances/{live['id']}/deliveries"
    for index in range(25):
        container.state.deliveries.append(
            {
                "id": f"d{index:02}",
                "owner_id": live["owner_id"],
                "live_instance_id": live["id"],
                "event_id": "event",
                "destination_encrypted": "secret",
                "created_at": "2026-10-23",
                "status": "delivered",
                "attempts": 1,
            }
        )
    container.state.deliveries.append(
        {"id": "other", "owner_id": "other", "live_instance_id": live["id"]}
    )
    result = client.get(path + "?page=2").get_json()["data"]
    assert result["page"] == 2 and result["total"] == 25 and len(result["items"]) == 5
    assert result["items"][0]["id"] == "d04"
    assert "destination_encrypted" not in result["items"][0]
    assert client.get(path + "?page=0").status_code == 400
    assert client.get(path + "?page=invalid").status_code == 400
    assert client.get("/api/v1/live-instances/unknown/deliveries").status_code == 404


def test_rename_legacy_and_running_backtests_survives_worker_save():
    container, client, headers, _ = setup()
    stale = deepcopy(container.backtests.get("b"))
    path = "/api/v1/backtests/b"
    for status in ("succeeded", "running"):
        container.backtests.update_status("b", {"status": status})
        assert (
            client.patch(path, headers=headers, json={"name": "  历史改名  "}).get_json()["data"][
                "name"
            ]
            == "历史改名"
        )
        container.backtests.save({**stale, "status": "succeeded", "name": "worker旧名称"}, b"[]")
        assert client.get(path).get_json()["data"]["name"] == "历史改名"
    for name in ("", " ", "x" * 161, None, 42):
        assert client.patch(path, headers=headers, json={"name": name}).status_code == 400
    container.backtests.update_status("b", {"owner_id": "other"})
    assert client.patch(path, headers=headers, json={"name": "越权"}).status_code == 404

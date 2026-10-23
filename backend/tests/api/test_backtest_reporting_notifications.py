import hashlib
import json
from copy import deepcopy

from tests.api.test_run_context import setup


def test_backtest_names_validation_fallback_and_persisted_performance_paging():
    c, client, headers, _ = setup()
    payload = {
        "strategy_version_id": "v1",
        "start_day": "2026-10-01",
        "end_day": "2026-10-20",
        "initial_cash": "1000",
    }
    named = client.post(
        "/api/v1/backtests", json=payload | {"name": "  十月验证  "}, headers=headers
    )
    assert named.status_code == 202
    run = named.get_json()["data"]
    assert run["name"] == "十月验证"
    assert client.get(f"/api/v1/backtests/{run['id']}").get_json()["data"]["name"] == "十月验证"
    default = client.post("/api/v1/backtests", json=payload, headers=headers).get_json()["data"]
    assert "原策略" in default["name"] and "2026-10-20" in default["name"]
    assert (
        client.post(
            "/api/v1/backtests", json=payload | {"name": "长" * 161}, headers=headers
        ).status_code
        == 422
    )
    run.update(
        status="succeeded",
        symbol_performance=[
            {"symbol": "b", "profit": "2"},
            {"symbol": "a", "profit": "100"},
            {"symbol": "c", "profit": None},
        ],
    )
    c.backtests.save(run, b"[]")
    path = f"/api/v1/backtests/{run['id']}/stock-performance"
    data = client.get(path + "?page=2&page_size=1").get_json()["data"]
    assert data["total"] == 3 and data["items"][0]["symbol"] == "b"
    assert client.get(path + "?page=0").status_code == 400
    run["owner_id"] = "other"
    assert client.get(path).status_code == 404


def test_legacy_performance_uses_frozen_snapshot_and_does_not_rewrite():
    c, client, _, _ = setup()
    run = c.backtests.get("b")
    assert run is not None
    raw = json.dumps([{"symbol": "000001", "trading_day": "2026-10-20", "close": "12"}]).encode()
    run.update(
        snapshot_id=hashlib.sha256(raw).hexdigest(),
        periods=[{"trading_day": "2026-10-20"}],
        trades=[
            {
                "symbol": "000001",
                "action": "buy",
                "quantity": "100",
                "price": "10",
                "fee": "1",
                "trading_day": "2026-10-19",
            }
        ],
    )
    c.backtests.save(run, raw)
    original = deepcopy(run)
    data = client.get("/api/v1/backtests/b/stock-performance").get_json()["data"]
    assert data["items"][0]["profit"] == "199"
    assert c.backtests.get("b") == original


def test_disabled_channel_edit_reveal_privacy_validation_and_paginated_lists():
    c, client, headers, _ = setup()
    assert c.secret_box is not None
    result = client.get("/api/v1/notifications/subscriptions/disabled")
    assert result.status_code == 200 and result.headers["Cache-Control"] == "no-store"
    assert result.get_json()["data"]["destination"] != "***"
    assert client.get("/api/v1/notifications/subscriptions/other").status_code == 404
    update = client.patch(
        "/api/v1/notifications/subscriptions/disabled",
        json={"name": "编辑停用渠道", "destination": "new-private-topic", "enabled": False},
        headers=headers,
    )
    assert update.status_code == 200 and "new-private-topic" not in update.text
    row = next(row for row in c.state.subscriptions if row["id"] == "disabled")
    assert (
        not row["enabled"]
        and c.secret_box.decrypt(row["destination_encrypted"]) == "new-private-topic"
    )
    assert "new-private-topic" not in str(c.state.audit_events)
    assert (
        "new-private-topic"
        not in client.get("/api/v1/notifications/subscriptions?page=1&page_size=2").text
    )
    original = deepcopy(row)
    invalid = client.patch(
        "/api/v1/notifications/subscriptions/disabled",
        json={"name": "不能部分保存", "destination": " "},
        headers=headers,
    )
    assert invalid.status_code == 400 and row == original
    owner = row["owner_id"]
    for index in range(23):
        c.state.deliveries.append(
            {
                "id": f"d{index:02}",
                "owner_id": owner,
                "created_at": f"2026-10-{index + 1:02}T00:00:00Z",
                "status": "delivered",
                "body": "private-body",
            }
        )
    c.state.deliveries.append({"id": "private", "owner_id": "other"})
    data = client.get("/api/v1/notifications/deliveries?page=2&page_size=10").get_json()["data"]
    assert data["total"] == 23 and data["items"][0]["id"] == "d12" and len(data["items"]) == 10
    assert "private-body" not in str(data) and "destination_encrypted" not in str(data)
    assert client.get("/api/v1/notifications/deliveries?page=bad").status_code == 400
    assert client.get("/api/v1/notifications/subscriptions?page_size=101").status_code == 400

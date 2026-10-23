from copy import deepcopy

from easy_quant.bootstrap import _default_datasets, ensure_dataset_catalog
from tests.api.test_run_context import setup


def test_termination_freezes_balances_and_never_reads_market_data(monkeypatch):
    c, client, headers, payload = setup()
    live = client.post("/api/v1/live-instances", json=payload, headers=headers).get_json()["data"]
    identifier = live["id"]
    c.state.recommendations[identifier] = [
        {
            "id": "r",
            "owner_id": live["owner_id"],
            "instrument_id": "000001",
            "action": "buy",
            "quantity": "100",
            "suggested_price": "10",
            "suggested_fee": "1",
            "status": "pending",
            "version": 0,
            "reason": "test",
        }
    ]

    def forbidden(*_args, **_kwargs):
        raise AssertionError("已终止实盘不得读取行情计算收益")

    monkeypatch.setattr(c.market_data, "list_bars", forbidden)
    prefix = f"/api/v1/live-instances/{identifier}"
    result = client.post(prefix + "/terminate", headers=headers).get_json()["data"]
    assert result["frozen_balances"]["cash"] == "2000.25"
    assert result["frozen_balances"]["positions"] == {"000001": "100"}
    assert result["terminated_at"]
    frozen = deepcopy(c.state.live_instances[identifier])
    for path in (prefix, prefix + "/portfolio"):
        data = client.get(path).get_json()["data"]
        portfolio = data.get("portfolio", data)
        assert portfolio["profit"] is None and portfolio["curve"] == []
    assert client.post(prefix + "/pause", headers=headers).status_code == 409
    assert (
        client.post(
            "/api/v1/recommendations/r/confirm",
            headers=headers,
            json={"expected_version": 0, "idempotency_key": "freeze-action"},
        ).status_code
        == 409
    )
    assert client.post(prefix + "/terminate", headers=headers).get_json()["data"] == frozen
    assert c.state.live_instances[identifier] == frozen


def test_live_list_pages_search_status_and_owner_scope():
    c, client, headers, payload = setup()
    live = client.post("/api/v1/live-instances", json=payload, headers=headers).get_json()["data"]
    for index in range(25):
        c.state.live_instances[f"copy-{index}"] = {
            **live,
            "id": f"copy-{index}",
            "name": "测试组合",
            "status": "terminated",
        }
    c.state.live_instances["private"] = {
        **live,
        "id": "private",
        "name": "测试组合",
        "owner_id": "other",
        "status": "terminated",
    }
    result = client.get(
        "/api/v1/live-instances?page=2&search=测试组合&status=terminated"
    ).get_json()["data"]
    assert result["total"] == 25 and len(result["items"]) == 5
    assert client.get("/api/v1/live-instances?page=0").status_code == 400
    assert client.get("/api/v1/live-instances?status=bad").status_code == 400
    assert isinstance(client.get("/api/v1/live-instances").get_json()["data"], list)


def test_missing_catalog_is_repaired_without_resetting_source_preferences():
    rows = [
        {"key": "securities", "name": "证券列表", "sources": [{"key": "akshare", "enabled": False}]}
    ]
    original = deepcopy(rows[0])
    ensure_dataset_catalog(rows)
    ensure_dataset_catalog(rows)
    assert len(rows) == len(_default_datasets()) and rows[0] == original
    assert {row["key"] for row in rows} >= {"daily-bars", "trading-calendar"}

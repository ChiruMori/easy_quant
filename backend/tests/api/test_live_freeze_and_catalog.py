from copy import deepcopy
from datetime import timedelta

from easy_quant.bootstrap import _default_datasets, ensure_dataset_catalog
from tests.api.test_run_context import setup
from tests.fakes.core import FixedClock


def test_termination_freezes_balances_and_profit_then_never_reads_market_data(monkeypatch):
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

    now = c.authentication.clock.now()
    c.state.live_instances[identifier]["started_at"] = (now - timedelta(days=1)).isoformat()
    c.market_data.upsert_bars(
        [
            {
                "symbol": "000001",
                "trading_day": at.date().isoformat(),
                "available_at": at.isoformat(),
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": "1",
            }
            for at, price in (
                (now - timedelta(days=1), "10"),
                (now, "12"),
                (now + timedelta(days=1), "99"),
            )
        ]
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("已终止实盘不得读取行情计算收益")

    prefix = f"/api/v1/live-instances/{identifier}"
    result = client.post(prefix + "/terminate", headers=headers).get_json()["data"]
    assert isinstance(c.authentication.clock, FixedClock)
    c.authentication.clock.advance(timedelta(hours=1))
    monkeypatch.setattr(c.market_data, "list_bars", forbidden)
    assert result["frozen_balances"]["cash"] == "2000.25"
    assert result["frozen_balances"]["positions"] == {"000001": "100"}
    assert result["terminated_at"]
    assert result["frozen_portfolio"]["profit"] == "200.00"
    assert len(result["frozen_portfolio"]["curve"]) == 2
    frozen = deepcopy(c.state.live_instances[identifier])
    for path in (prefix, prefix + "/portfolio"):
        data = client.get(path).get_json()["data"]
        portfolio = data.get("portfolio", data)
        assert portfolio == result["frozen_portfolio"]
    metrics = client.get(prefix + "/portfolio?view=metrics").get_json()["data"]
    assert metrics["return_rate"] == result["frozen_portfolio"]["return_rate"]
    assert "curve" not in metrics
    page = client.get("/api/v1/live-instances?page=1").get_json()["data"]
    assert page["items"][0]["return_rate"] == metrics["return_rate"]
    assert "frozen_portfolio" not in page["items"][0]
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


def test_legacy_terminated_profit_is_rebuilt_once_at_recorded_end(monkeypatch):
    c, client, headers, payload = setup()
    item = client.post("/api/v1/live-instances", json=payload, headers=headers).get_json()["data"]
    prefix = f"/api/v1/live-instances/{item['id']}"
    client.post(prefix + "/terminate", headers=headers)
    original = c.state.live_instances[item["id"]].pop("frozen_portfolio")
    c.state.live_instances[item["id"]].pop("terminated_at")
    rebuilt = client.get(prefix + "/portfolio").get_json()["data"]
    assert rebuilt == original

    def forbidden(*_args):
        raise AssertionError("历史快照只能重建一次")

    monkeypatch.setattr(c.market_data, "list_bars", forbidden)
    assert client.get(prefix + "/portfolio").get_json()["data"] == rebuilt


def test_termination_rejects_concurrent_bookkeeping_changes(monkeypatch):
    c, client, headers, payload = setup()
    live = client.post("/api/v1/live-instances", json=payload, headers=headers).get_json()["data"]

    def changed(*_args):
        c.state.live_instances[live["id"]]["capital_added"] = "100"
        return []

    monkeypatch.setattr(c.market_data, "list_bars", changed)
    assert (
        client.post(f"/api/v1/live-instances/{live['id']}/terminate", headers=headers).status_code
        == 409
    )
    assert c.state.live_instances[live["id"]]["status"] == "active"


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

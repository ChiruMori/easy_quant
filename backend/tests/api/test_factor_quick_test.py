from easy_quant.api.app import create_app
from tests.api.test_strategy_library import authenticated
from tests.fakes.platform import make_test_container


def test_factor_catalog_statistics_and_authenticated_synchronous_quick_test():
    container = make_test_container(initialize_admin=True)
    anonymous = create_app(settings=container.settings, container=container).test_client()
    assert anonymous.post("/api/v1/factors/technical.ma/quick-test", json={}).status_code == 401
    client, headers = authenticated(container)
    container.factor_statistics.record(
        "phase", {"technical.ma": {"calls": 2, "elapsed_ns": 6_000_000}}
    )
    ma = next(
        row
        for row in client.get("/api/v1/factors").get_json()["data"]
        if row["key"] == "technical.ma"
    )
    assert (ma["calls"], ma["total_ms"], ma["average_ms"]) == (2, 6, 3)
    before = container.factor_statistics.snapshot()
    response = client.post(
        "/api/v1/factors/technical.ma/quick-test",
        headers=headers,
        json={"trading_day": "2026-09-25", "parameters": {"symbol": "a"}},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["result"]["available"] is False
    assert container.factor_statistics.snapshot() == before
    assert (
        client.post("/api/v1/factors/technical.ma/quick-test", headers=headers, json={}).status_code
        == 400
    )

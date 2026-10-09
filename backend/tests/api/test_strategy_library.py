from datetime import UTC, date, datetime
from typing import cast

from easy_quant.api.app import create_app
from tests.fakes.core import FixedClock
from tests.fakes.platform import make_test_container


def authenticated(container):
    client = create_app(settings=container.settings, container=container).test_client()
    response = client.post(
        "/api/v1/auth/login",
        json={
            "username": "admin",
            "password": container.settings.initial_admin_password.get_secret_value(),
        },
    )
    return client, {"X-CSRF-Token": response.get_json()["data"]["csrf_token"]}


def test_library_requires_login_and_documents_common_context():
    container = make_test_container(initialize_admin=True)
    client = create_app(settings=container.settings, container=container).test_client()
    assert client.get("/api/v1/strategy-library").status_code == 401
    client, _ = authenticated(container)
    entries = client.get("/api/v1/strategy-library").get_json()["data"]
    signatures = " ".join(item["signature"] for item in entries)
    assert "context.store" in signatures and "context.signal" in signatures
    assert all(item["example"] and item["runtime"] for item in entries)


def test_coverage_waits_for_publication_and_hides_unavailable_target():
    container = make_test_container(initialize_admin=True)
    container.market_data.upsert_instruments([{"symbol": "000001", "name": "测试"}])
    container.market_data.upsert_bars(
        [
            {
                "symbol": "000001",
                "trading_day": "2026-01-01",
                "open": "10",
                "high": "11",
                "low": "9",
                "close": "10",
                "volume": "1",
            },
            {
                "symbol": "000001",
                "trading_day": "2026-09-28",
                "open": "10",
                "high": "11",
                "low": "9",
                "close": "10",
                "volume": "1",
            },
        ]
    )
    clock = cast(FixedClock, container.authentication.clock)
    container.market_data.upsert_trading_days([date(2026, 9, 29)])
    clock.current = datetime(2026, 9, 29, 6, tzinfo=UTC)
    client, _ = authenticated(container)
    url = "/api/v1/admin/market-data/coverage"
    row = client.get(url).get_json()["data"]["items"][0]
    assert row["stale"] is False and row["recommended_end_day"] == "2026-09-28"
    clock.current = datetime(2026, 9, 29, 14, 1, tzinfo=UTC)
    assert client.get(url).get_json()["data"]["items"][0]["stale"] is True
    container.market_data.upsert_records(
        "daily-bar-availability",
        [
            {
                "symbol": "000001",
                "requested_end_day": "2026-09-29",
                "record_key": "000001:2026-09-29",
                "latest_day": "2026-09-28",
                "available_at": clock.now().isoformat(),
            }
        ],
    )
    row = client.get(url).get_json()["data"]["items"][0]
    assert row["publication_pending"] is True and row["stale"] is False


def test_live_uses_one_system_intraday_schedule_without_default_after_market():
    container = make_test_container(initialize_admin=True)
    client, headers = authenticated(container)
    owner = container.authentication.repository.get_user_by_username("admin")
    assert owner is not None
    container.backtests.save(
        {
            "id": "b",
            "owner_id": owner.id,
            "strategy_version_id": "v",
            "status": "succeeded",
            "config": {"initial_cash": "10000", "parameters": {"ratio": "0.2"}},
        },
        b"",
    )
    response = client.post("/api/v1/live-instances", json={"backtest_id": "b"}, headers=headers)
    assert response.status_code == 201
    schedules = list(container.state.schedules.values())
    assert len(schedules) == 2
    intraday = next(row for row in schedules if row["configuration"]["phase"] == "on_market")
    assert (
        intraday["schedule_kind"] == "cron" and intraday["schedule_expression"] == "50 14 * * 1-5"
    )
    assert response.get_json()["data"]["parameters"] == {"ratio": "0.2"}

from dataclasses import replace
from datetime import date, timedelta

from easy_quant.api.app import create_app
from easy_quant.domain.identity.entities import UserRole
from tests.api.test_strategy_library import authenticated
from tests.fakes.platform import make_test_container


def test_instrument_reads_require_login_and_do_not_grant_maintenance_permissions():
    container = make_test_container(initialize_admin=True)
    container.market_data.upsert_instruments([{"symbol": "000001", "name": "平安银行"}])
    bars = [
        {
            "symbol": "000001",
            "trading_day": (date(2020, 1, 1) + timedelta(days=index)).isoformat(),
            "open": "10",
            "close": "10.1",
            "high": "11",
            "low": "9",
            "volume": "100",
        }
        for index in range(1100)
    ]
    container.market_data.upsert_bars(bars)
    anonymous = create_app(settings=container.settings, container=container).test_client()
    prefix = "/api/v1/market-data/instruments/000001"
    assert anonymous.get(prefix).status_code == 401
    assert anonymous.get(prefix + "/daily-bars").status_code == 401
    client, headers = authenticated(container)
    user = container.authentication.repository.get_user_by_username("admin")
    assert user
    container.authentication.repository.save_user(replace(user, role=UserRole.USER))
    assert client.get(prefix).get_json()["data"]["name"] == "平安银行"
    result = client.get(prefix + "/daily-bars").get_json()["data"]
    assert len(result) == 180 and result[0]["trading_day"] == bars[-180]["trading_day"]
    result = client.get(prefix + "/daily-bars?start_day=2020-01-01").get_json()["data"]
    assert len(result) == 1000
    result = client.get(prefix + "/daily-bars?start_day=2020-01-02&end_day=2020-01-06").get_json()[
        "data"
    ]
    assert [row["trading_day"] for row in result] == [row["trading_day"] for row in bars[1:6]]
    assert client.get("/api/v1/market-data/instruments/999999").status_code == 404
    assert client.get("/api/v1/admin/market-data/instruments/000001").status_code == 403
    assert (
        client.put(
            "/api/v1/admin/market-data/instruments/000001/status",
            headers=headers,
            json={"status": "suspended", "reason": "交易所公告"},
        ).status_code
        == 403
    )
    assert client.put(prefix + "/status", headers=headers, json={}).status_code == 404

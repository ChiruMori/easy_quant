from dataclasses import replace

from easy_quant.api.app import create_app
from easy_quant.domain.identity.entities import UserRole
from tests.fakes.platform import make_test_container


def test_fundamentals_require_login_and_expose_only_requested_stock_and_past_records():
    container = make_test_container(initialize_admin=True)
    client = create_app(settings=container.settings, container=container).test_client()
    root = "/api/v1/market-data/instruments/000001/fundamentals"
    assert client.get(root).status_code == 401
    client.post(
        "/api/v1/auth/login",
        json={
            "username": container.settings.initial_admin_username,
            "password": container.settings.initial_admin_password.get_secret_value(),
        },
    )
    user = container.authentication.repository.get_user_by_username(
        container.settings.initial_admin_username
    )
    assert user
    container.authentication.repository.save_user(replace(user, role=UserRole.USER))
    container.market_data.upsert_instruments([{"symbol": "000001"}])
    container.market_data.upsert_records(
        "financial-indicators",
        [
            {"record_key": str(index), "symbol": symbol, "available_at": at, "roe": "8.07"}
            for index, symbol, at in [
                (1, "000001", "2026-03-01T00:00:00+00:00"),
                (2, "000001", "2026-06-01T00:00:00+00:00"),
                (3, "000002", "2026-03-01T00:00:00+00:00"),
                (4, "000001", "2026-10-01T00:00:00+00:00"),
            ]
        ],
    )
    overview = client.get(root).get_json()["data"]
    assert overview["fields"]["roe"] == {"label": "加权净资产收益率", "unit": "%"}
    assert (
        next(row for row in overview["datasets"] if row["key"] == "financial-indicators")["count"]
        == 2
    )
    page = client.get(root + "/financial-indicators?page_size=1&page=2").get_json()["data"]
    assert page["total"] == 2 and page["items"][0]["record_key"] == "1"
    for query in ("?page=bad", "?page=0", "?page_size=51"):
        assert client.get(root + "/financial-indicators" + query).status_code == 400
    assert client.get(root + "/not-public").status_code == 400
    assert client.get(root.replace("000001", "999999")).status_code == 404
    assert client.get("/api/v1/admin/market-data/datasets").status_code == 403

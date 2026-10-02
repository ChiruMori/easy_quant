import io
from datetime import UTC, datetime

from pydantic import SecretStr

from easy_quant.api.app import create_app
from easy_quant.application.services.authentication import AuthenticationService
from easy_quant.bootstrap import Container
from easy_quant.config import Settings
from easy_quant.infrastructure.persistence.repositories.in_memory_identity import (
    InMemoryIdentityRepository,
)
from tests.fakes.core import FixedClock, SequentialIdGenerator


def make_client():
    settings = Settings(
        database_url=SecretStr("mysql+pymysql://test-only.invalid/easy_quant"),
        secret_key=SecretStr("test-secret"),
    )
    auth = AuthenticationService(
        InMemoryIdentityRepository(),
        FixedClock(datetime(2026, 9, 29, tzinfo=UTC)),
        SequentialIdGenerator(),
    )
    app = create_app(settings=settings, container=Container(settings, auth))
    app.config.update(TESTING=True)
    return app.test_client()


def test_admin_data_requires_authentication() -> None:
    assert make_client().get("/api/v1/admin/market-data/datasets").status_code == 401


def test_raw_cache_has_no_public_endpoint() -> None:
    assert make_client().get("/api/v1/raw-cache").status_code == 404


def test_admin_can_list_datasets() -> None:
    client = make_client()
    client.post(
        "/api/v1/auth/initialize", json={"username": "admin", "password": "very-secure-password"}
    )
    client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "very-secure-password"}
    )
    response = client.get("/api/v1/admin/market-data/datasets")
    assert response.status_code == 200
    body = response.get_json()
    assert body is not None
    assert body["data"][0]["sources"]


def test_csv_commit_updates_market_data_coverage() -> None:
    client = make_client()
    client.post(
        "/api/v1/auth/initialize", json={"username": "admin", "password": "very-secure-password"}
    )
    login = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "very-secure-password"}
    )
    headers = {"X-CSRF-Token": login.get_json()["data"]["csrf_token"]}
    csv_body = (
        "symbol,trading_day,open,high,low,close,volume\n"
        "000001,2026-09-29,10.00,10.20,9.90,10.10,12345\n"
    )
    preview = client.post(
        "/api/v1/admin/market-data/imports/preview",
        data={"file": (io.BytesIO(csv_body.encode()), "bars.csv")},
        content_type="multipart/form-data",
        headers=headers,
    ).get_json()["data"]
    assert preview["valid"] is True
    committed = client.post(
        "/api/v1/admin/market-data/imports/commit",
        json={"preview_id": preview["preview_id"]},
        headers=headers,
    )
    assert committed.status_code == 201
    coverage = client.get("/api/v1/admin/market-data/coverage").get_json()["data"]
    assert coverage["instrument_count"] == 1
    assert coverage["items"][0]["sync_status"] == "数据不足"


def test_coverage_uses_aggregate_without_loading_daily_rows(monkeypatch) -> None:
    from datetime import date

    from tests.fakes.platform import make_test_container

    container = make_test_container(initialize_admin=True)
    monkeypatch.setattr(
        container.market_data,
        "list_bars",
        lambda *_args: (_ for _ in ()).throw(AssertionError("不得加载全部日线")),
    )
    monkeypatch.setattr(
        container.market_data,
        "bar_coverage",
        lambda: {
            "000001": {"first_day": date(1991, 4, 3), "last_day": date(2026, 9, 30), "count": 8000}
        },
    )
    client = create_app(settings=container.settings, container=container).test_client()
    client.post(
        "/api/v1/auth/login",
        json={
            "username": "admin",
            "password": container.settings.initial_admin_password.get_secret_value(),
        },
    )
    data = client.get("/api/v1/admin/market-data/coverage").get_json()["data"]
    assert data["instrument_count"] == 1
    assert data["items"][0]["record_count"] == 8000
    assert data["items"][0]["sync_status"] == "完全同步"

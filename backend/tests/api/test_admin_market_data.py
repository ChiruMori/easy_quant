import io
from datetime import UTC, datetime
from typing import Any, cast

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


def test_coverage_is_paginated_and_searchable_with_status_filter() -> None:
    from tests.fakes.platform import make_test_container

    container = make_test_container(initialize_admin=True)
    container.market_data.upsert_instruments(
        [
            {
                "symbol": f"{index:06d}",
                "name": "平安银行" if index == 1 else f"股票{index}",
                "exchange": "深圳证券交易所",
            }
            for index in range(6001)
        ]
    )
    container.market_data.upsert_bars(
        [
            {
                "symbol": "000001",
                "trading_day": day,
                "open": "10",
                "high": "11",
                "low": "9",
                "close": "10.5",
                "volume": "100",
                "available_at": f"{day}T15:00:00+08:00",
            }
            for day in ("2015-01-05", "2026-09-29")
        ]
    )
    app = create_app(settings=container.settings, container=container)
    client = app.test_client()
    client.post(
        "/api/v1/auth/login",
        json={
            "username": container.settings.initial_admin_username,
            "password": container.settings.initial_admin_password.get_secret_value(),
        },
    )
    first = client.get("/api/v1/admin/market-data/coverage?page=1&page_size=50").get_json()["data"]
    assert first["instrument_count"] == 6001
    assert first["total"] == 6001
    assert len(first["items"]) == 50
    second = client.get("/api/v1/admin/market-data/coverage?page=2&page_size=50").get_json()["data"]
    assert second["items"][0]["symbol"] == "000050"
    via_cursor = client.get(
        "/api/v1/admin/market-data/coverage?page=2&page_size=50&after=000049"
    ).get_json()["data"]
    assert via_cursor["items"][0]["symbol"] == "000050"
    backward = client.get(
        "/api/v1/admin/market-data/coverage?page=1&page_size=50&before=000050"
    ).get_json()["data"]
    assert backward["items"][0]["symbol"] == "000000"
    jumped = client.get("/api/v1/admin/market-data/coverage?page=121&page_size=50").get_json()[
        "data"
    ]
    assert [item["symbol"] for item in jumped["items"]] == ["006000"]
    oversized = client.get(
        "/api/v1/admin/market-data/coverage?page=999999&page_size=50"
    ).get_json()["data"]
    assert oversized["page"] == 121
    assert client.get("/api/v1/admin/market-data/coverage?after=1&before=2").status_code == 400
    searched = client.get("/api/v1/admin/market-data/coverage?search=平安银行").get_json()["data"]
    assert searched["total"] == 1
    assert searched["items"][0]["symbol"] == "000001"
    filtered = client.get("/api/v1/admin/market-data/coverage?status=完全同步").get_json()["data"]
    assert filtered["total"] == 1
    assert filtered["items"][0]["symbol"] == "000001"
    detail = client.get("/api/v1/admin/market-data/instruments/000001").get_json()["data"]
    assert detail["name"] == "平安银行"
    bars = client.get(
        "/api/v1/admin/market-data/instruments/000001/daily-bars?start_day=2026-01-01"
    ).get_json()["data"]
    assert len(bars) == 1
    assert bars[0]["close"] == "10.5"


def test_sync_request_creates_job_before_data_source_runs() -> None:
    from easy_quant.infrastructure.core import SystemSleeper
    from easy_quant.worker.handlers.market_data import register_market_data_handlers
    from easy_quant.worker.registry import JobHandlerRegistry
    from easy_quant.worker.runner import Worker
    from tests.fakes.platform import make_test_container

    container = make_test_container(initialize_admin=True)

    class FakeDataSync:
        called = False

        def sync(self, *_args, **_kwargs):
            self.called = True
            return {"record_count": 2, "attempts": []}

    service = FakeDataSync()
    container.data_sync = cast(Any, service)
    app = create_app(settings=container.settings, container=container)
    client = app.test_client()
    login = client.post(
        "/api/v1/auth/login",
        json={
            "username": container.settings.initial_admin_username,
            "password": container.settings.initial_admin_password.get_secret_value(),
        },
    )
    response = client.post(
        "/api/v1/admin/market-data/acquisitions",
        json={
            "dataset_key": "daily-bars",
            "symbols": ["000001"],
            "start_day": "2026-09-01",
            "end_day": "2026-09-29",
        },
        headers={"X-CSRF-Token": login.get_json()["data"]["csrf_token"]},
    )
    assert response.status_code == 202
    task = response.get_json()["data"]
    assert task["status"] == "queued"
    assert 36 < len(task["job_id"]) <= 64
    assert service.called is False
    registry = JobHandlerRegistry()
    register_market_data_handlers(registry, container)
    Worker(
        "test-worker",
        container.jobs,
        registry,
        container.authentication.clock,
        SystemSleeper(),
    ).run_once()
    assert service.called is True
    updated = client.get(f"/api/v1/admin/market-data/acquisitions/{task['id']}").get_json()["data"]
    assert updated["status"] == "succeeded"
    assert updated["record_count"] == 2

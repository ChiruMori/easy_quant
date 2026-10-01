from datetime import UTC, date, datetime
from decimal import Decimal

from pydantic import SecretStr

from easy_quant.api.app import create_app
from easy_quant.application.services.authentication import AuthenticationService
from easy_quant.bootstrap import Container
from easy_quant.config import Settings
from easy_quant.infrastructure.persistence.repositories.in_memory_identity import (
    InMemoryIdentityRepository,
)
from tests.fakes.core import FixedClock, SequentialIdGenerator


def test_backtest_schema_rejects_reversed_dates() -> None:
    from pydantic import ValidationError

    from easy_quant.api.schemas.backtests import BacktestCreateRequest

    try:
        BacktestCreateRequest(
            strategy_version_id="v1",
            symbols=["000001"],
            start_day=date(2026, 2, 1),
            end_day=date(2026, 1, 1),
            initial_cash=Decimal("1000"),
        )
    except ValidationError:
        return
    raise AssertionError("应拒绝倒序日期")


def test_backtest_is_blocked_when_market_data_is_missing() -> None:
    settings = Settings(
        database_url=SecretStr("mysql+pymysql://test-only.invalid/easy_quant"),
        secret_key=SecretStr("test-secret"),
    )
    authentication = AuthenticationService(
        InMemoryIdentityRepository(),
        FixedClock(datetime(2026, 9, 29, tzinfo=UTC)),
        SequentialIdGenerator(),
    )
    app = create_app(settings=settings, container=Container(settings, authentication))
    app.config.update(TESTING=True)
    client = app.test_client()
    client.post(
        "/api/v1/auth/initialize", json={"username": "admin", "password": "very-secure-password"}
    )
    login = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "very-secure-password"}
    )
    headers = {"X-CSRF-Token": login.get_json()["data"]["csrf_token"]}
    strategy = client.post(
        "/api/v1/strategies",
        json={
            "name": "缺失数据测试",
            "description": "",
            "source_code": (
                "def before_market(context, parameters):\n    return []\n"
                "def on_market(context, parameters):\n    return []\n"
                "def after_market(context, parameters):\n    return []\n"
            ),
        },
        headers=headers,
    ).get_json()["data"]
    response = client.post(
        "/api/v1/backtests",
        json={
            "strategy_version_id": strategy["current_version_id"],
            "start_day": "2026-01-01",
            "end_day": "2026-01-31",
            "initial_cash": "100000",
        },
        headers=headers,
    )
    assert response.status_code == 409
    error = response.get_json()["error"]
    assert error["code"] == "state_conflict"
    assert error["details"]["action_url"] == "/admin/data"
    assert "模拟行情" not in error["message"]

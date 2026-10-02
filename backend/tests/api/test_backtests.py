from datetime import date
from decimal import Decimal

from easy_quant.api.app import create_app
from tests.fakes.platform import make_test_container


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


def test_backtest_missing_data_is_reported_by_worker() -> None:
    container = make_test_container(initialize_admin=True)
    app = create_app(settings=container.settings, container=container)
    app.config.update(TESTING=True)
    client = app.test_client()
    login = client.post(
        "/api/v1/auth/login",
        json={
            "username": container.settings.initial_admin_username,
            "password": container.settings.initial_admin_password.get_secret_value(),
        },
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
    assert response.status_code == 202
    run = response.get_json()["data"]
    assert run["status"] == "queued"

    from easy_quant.infrastructure.core import SystemSleeper
    from easy_quant.worker.handlers.backtests import register_backtest_handlers
    from easy_quant.worker.registry import JobHandlerRegistry
    from easy_quant.worker.runner import Worker

    registry = JobHandlerRegistry()
    register_backtest_handlers(registry, container)
    Worker(
        "test-worker",
        container.jobs,
        registry,
        container.authentication.clock,
        SystemSleeper(),
    ).run_once()
    failed = client.get(f"/api/v1/backtests/{run['id']}").get_json()["data"]
    assert failed["status"] == "failed"
    assert "行情数据尚未同步" in failed["error"]

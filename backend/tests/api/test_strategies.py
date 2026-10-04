from datetime import date
from unittest.mock import patch

from easy_quant.api.app import create_app
from easy_quant.application.services.strategy_quick_test import quick_test_start_day
from easy_quant.infrastructure.core import SystemSleeper
from easy_quant.worker.handlers.strategies import register_strategy_handlers
from easy_quant.worker.registry import JobHandlerRegistry
from easy_quant.worker.runner import Worker
from tests.fakes.platform import make_test_container


def _client_and_container():
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
    return client, container, {"X-CSRF-Token": login.get_json()["data"]["csrf_token"]}


def _run_worker_once(container) -> None:
    registry = JobHandlerRegistry()
    register_strategy_handlers(registry, container)
    Worker(
        "test-worker",
        container.jobs,
        registry,
        container.authentication.clock,
        SystemSleeper(),
    ).run_once()


def _create_strategy(client, headers, source_code: str):
    return client.post(
        "/api/v1/strategies",
        headers=headers,
        json={"name": "demo", "source_code": source_code},
    ).get_json()["data"]


def test_create_and_run_strategy_api_uses_worker_job() -> None:
    client, container, headers = _client_and_container()
    container.market_data.upsert_bars(
        [
            {
                "symbol": "000001",
                "trading_day": "2026-09-29",
                "open": "10",
                "high": "11",
                "low": "9",
                "close": "10.5",
                "volume": "100",
                "available_at": "2026-09-29T15:00:00+08:00",
            }
        ]
    )
    strategy = _create_strategy(
        client,
        headers,
        "def before_market(context, parameters):\n return []\n"
        "def on_market(context, parameters):\n return []\n"
        "def after_market(context, parameters):\n print('done')\n return []",
    )
    queued = client.post(
        f"/api/v1/strategies/{strategy['id']}/run",
        headers=headers,
        json={"trading_day": "2026-09-29", "parameters": {}},
    )
    assert queued.status_code == 202
    assert queued.get_json()["data"]["status"] == "queued"
    assert 36 < len(queued.get_json()["data"]["id"]) <= 64
    assert len(container.jobs.list_all()) == 1

    with patch.object(
        container.market_data,
        "list_runtime_bars",
        wraps=container.market_data.list_runtime_bars,
    ) as bars:
        _run_worker_once(container)
    bars.assert_called_once_with(
        date(2026, 9, 29),
        date(2026, 9, 29),
    )
    runs = client.get(f"/api/v1/strategies/{strategy['id']}/runs").get_json()["data"]
    assert runs[0]["status"] == "succeeded"
    assert runs[0]["phase_results"][2]["stdout"] == "done\n"


def test_quick_test_history_uses_five_previous_trading_days_across_weekend() -> None:
    days = {date(2026, 9, day) for day in (18, 21, 22, 23, 24, 25, 28, 29)}
    assert quick_test_start_day(days, date(2026, 9, 29)) == date(2026, 9, 22)
    assert quick_test_start_day({date(2026, 9, 28)}, date(2026, 9, 29)) == date(2026, 9, 28)
    assert quick_test_start_day(set(), date(2026, 9, 29)) == date(2026, 9, 29)


def test_sample_moving_average_returns_many_signals_through_worker() -> None:
    client, container, headers = _client_and_container()
    days = ("2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25", "2026-09-28")
    container.market_data.upsert_bars(
        [
            {
                "symbol": f"{index:06d}",
                "trading_day": day,
                "open": str(10 + offset),
                "high": str(11 + offset),
                "low": str(9 + offset),
                "close": str(10 + offset),
                "volume": "100",
                "available_at": f"{day}T15:00:00+08:00",
            }
            for offset, day in enumerate(days)
            for index in range(3000)
        ]
    )
    template = client.get("/api/v1/strategies/templates").get_json()["data"][0]
    strategy = _create_strategy(client, headers, template["source_code"])
    queued = client.post(
        f"/api/v1/strategies/{strategy['id']}/run",
        headers=headers,
        json={"trading_day": "2026-09-28", "parameters": {}},
    )
    assert queued.status_code == 202
    _run_worker_once(container)
    run = client.get(f"/api/v1/strategies/{strategy['id']}/runs").get_json()["data"][0]
    assert run["status"] == "succeeded"
    assert len(run["phase_results"][0]["signals"]) == 3000
    assert run["phase_results"][0]["stdout"] == ""


def test_built_in_template_failure_is_recorded_on_job() -> None:
    client, container, headers = _client_and_container()
    template = client.get("/api/v1/strategies/templates").get_json()["data"][0]
    strategy = _create_strategy(client, headers, template["source_code"])
    response = client.post(
        f"/api/v1/strategies/{strategy['id']}/run",
        headers=headers,
        json={"trading_day": "2026-09-29", "parameters": {"quantity": 100}},
    )
    assert response.status_code == 202
    _run_worker_once(container)
    run = client.get(f"/api/v1/strategies/{strategy['id']}/runs").get_json()["data"][0]
    assert run["status"] == "failed"
    assert "日线数据" in run["error"]


def test_quick_test_excludes_bars_not_yet_available_at_decision_time() -> None:
    client, container, headers = _client_and_container()
    container.market_data.upsert_bars(
        [
            {
                "symbol": "000001",
                "trading_day": "2026-09-28",
                "open": "10",
                "high": "11",
                "low": "9",
                "close": "10.5",
                "volume": "100",
                "available_at": "2026-09-30T15:00:00+08:00",
            },
            {
                "symbol": "000001",
                "trading_day": "2026-09-29",
                "open": "11",
                "high": "12",
                "low": "10",
                "close": "11.5",
                "volume": "100",
                "available_at": "2026-09-29T15:00:00+08:00",
            },
        ]
    )
    source = (
        "def before_market(context, parameters):\n"
        " print(len(context.factor('market.daily-bars', symbol='000001')))\n return []\n"
        "def on_market(context, parameters):\n return []\n"
        "def after_market(context, parameters):\n"
        " print(len(context.factor('market.daily-bars', symbol='000001')))\n return []"
    )
    strategy = _create_strategy(client, headers, source)
    client.post(
        f"/api/v1/strategies/{strategy['id']}/run",
        headers=headers,
        json={"trading_day": "2026-09-29", "parameters": {}},
    )
    _run_worker_once(container)
    run = client.get(f"/api/v1/strategies/{strategy['id']}/runs").get_json()["data"][0]
    assert run["status"] == "succeeded"
    assert run["phase_results"][0]["stdout"] == "0\n"
    assert run["phase_results"][2]["stdout"] == "1\n"

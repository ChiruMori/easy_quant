from easy_quant.api.app import create_app
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

    _run_worker_once(container)
    runs = client.get(f"/api/v1/strategies/{strategy['id']}/runs").get_json()["data"]
    assert runs[0]["status"] == "succeeded"
    assert runs[0]["phase_results"][2]["stdout"] == "done\n"


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

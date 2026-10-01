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


def test_create_and_run_strategy_api() -> None:
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
    client = app.test_client()
    client.post(
        "/api/v1/auth/initialize", json={"username": "user", "password": "very-secure-password"}
    )
    login = client.post(
        "/api/v1/auth/login", json={"username": "user", "password": "very-secure-password"}
    )
    csrf = login.get_json()["data"]["csrf_token"]
    headers = {"X-CSRF-Token": csrf}
    created = client.post(
        "/api/v1/strategies",
        headers=headers,
        json={
            "name": "demo",
            "source_code": (
                "def before_market(context, parameters):\n return []\n"
                "def on_market(context, parameters):\n return []\n"
                "def after_market(context, parameters):\n return []"
            ),
        },
    )
    assert created.status_code == 201
    strategy_id = created.get_json()["data"]["id"]
    run = client.post(
        f"/api/v1/strategies/{strategy_id}/run", headers=headers, json={"parameters": {}}
    )
    assert run.status_code == 200
    assert run.get_json()["data"]["status"] == "succeeded"


def test_built_in_templates_are_valid_but_blocked_without_real_data() -> None:
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
    client = app.test_client()
    client.post(
        "/api/v1/auth/initialize",
        json={"username": "user", "password": "very-secure-password"},
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "user", "password": "very-secure-password"},
    )
    headers = {"X-CSRF-Token": login.get_json()["data"]["csrf_token"]}

    templates = client.get("/api/v1/strategies/templates").get_json()["data"]
    assert len(templates) >= 2
    for index, template in enumerate(templates):
        created = client.post(
            "/api/v1/strategies",
            headers=headers,
            json={"name": f"template-{index}", "source_code": template["source_code"]},
        )
        strategy_id = created.get_json()["data"]["id"]
        result = client.post(
            f"/api/v1/strategies/{strategy_id}/run",
            headers=headers,
            json={"parameters": {"quantity": 100}},
        )
        assert result.status_code == 409
        assert result.get_json()["error"]["code"] == "state_conflict"

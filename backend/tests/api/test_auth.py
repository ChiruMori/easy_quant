from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import SecretStr

from easy_quant.api.app import create_app
from easy_quant.application.services.authentication import AuthenticationService
from easy_quant.bootstrap import Container
from easy_quant.config import Settings
from easy_quant.infrastructure.persistence.repositories.in_memory_identity import (
    InMemoryIdentityRepository,
)
from tests.fakes.core import FixedClock, SequentialIdGenerator


@pytest.fixture
def client():
    settings = Settings(
        database_url=SecretStr("mysql+pymysql://test-only.invalid/easy_quant"),
        secret_key=SecretStr("test-secret"),
    )
    service = AuthenticationService(
        InMemoryIdentityRepository(),
        FixedClock(datetime(2026, 9, 29, tzinfo=UTC)),
        SequentialIdGenerator(),
    )
    app = create_app(settings=settings, container=Container(settings, service))
    app.config.update(TESTING=True)
    return app.test_client()


def test_initialize_login_and_me(client) -> None:
    response = client.post(
        "/api/v1/auth/initialize",
        json={"username": "Admin", "password": "very-secure-password"},
    )
    assert response.status_code == 201
    assert response.json["data"]["role"] == "admin"

    duplicate = client.post(
        "/api/v1/auth/initialize",
        json={"username": "Other", "password": "very-secure-password"},
    )
    assert duplicate.status_code == 409

    login = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "very-secure-password"},
    )
    assert login.status_code == 200
    assert login.json["data"]["csrf_token"]

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json["data"]["user"]["username"] == "admin"


def test_invalid_password_does_not_reveal_user(client) -> None:
    client.post(
        "/api/v1/auth/initialize",
        json={"username": "admin", "password": "very-secure-password"},
    )
    response = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "wrong-password"}
    )
    assert response.status_code == 401


def test_me_requires_authentication(client) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401

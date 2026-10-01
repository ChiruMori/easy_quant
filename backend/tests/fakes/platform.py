from __future__ import annotations

from datetime import UTC, datetime

from pydantic import SecretStr

from easy_quant.application.services.authentication import AuthenticationService
from easy_quant.bootstrap import Container
from easy_quant.config import Settings
from easy_quant.infrastructure.persistence.repositories.in_memory_identity import (
    InMemoryIdentityRepository,
)
from easy_quant.infrastructure.persistence.repositories.jobs import InMemoryJobRepository
from tests.fakes.core import FixedClock, SequentialIdGenerator


def make_test_settings() -> Settings:
    """测试只注入边界替身；该 URL 不会建立连接。"""

    return Settings(
        database_url=SecretStr("mysql+pymysql://test-only.invalid/easy_quant"),
        secret_key=SecretStr("test-only-secret"),
        initial_admin_password=SecretStr("change-this-admin-password"),
    )


def make_test_container(
    settings: Settings | None = None,
    *,
    initialize_admin: bool = False,
) -> Container:
    settings = settings or make_test_settings()
    authentication = AuthenticationService(
        InMemoryIdentityRepository(),
        FixedClock(datetime(2026, 9, 29, 8, 0, tzinfo=UTC)),
        SequentialIdGenerator(),
    )
    container = Container(settings, authentication)
    container.jobs = InMemoryJobRepository()
    if initialize_admin:
        authentication.initialize_admin(
            settings.initial_admin_username,
            settings.initial_admin_password.get_secret_value(),
        )
    return container

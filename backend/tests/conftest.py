from __future__ import annotations

import random
import socket
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest


class NetworkAccessBlocked(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*_args: object, **_kwargs: object) -> None:
        raise NetworkAccessBlocked("自动化测试禁止访问网络；请使用 fake 或固定 fixture")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)


@pytest.fixture(autouse=True)
def deterministic_randomness() -> Iterator[None]:
    state = random.getstate()
    random.seed(20260929)
    yield
    random.setstate(state)


@pytest.fixture
def fixed_now() -> datetime:
    return datetime(2026, 9, 29, 8, 0, tzinfo=UTC)


@pytest.fixture
def workspace_tmp_path(tmp_path: Path) -> Path:
    return tmp_path

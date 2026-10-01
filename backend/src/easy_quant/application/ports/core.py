from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Protocol, TypeVar

T = TypeVar("T")


class Clock(Protocol):
    def now(self) -> datetime: ...


class Sleeper(Protocol):
    def sleep(self, seconds: float) -> None: ...


class IdGenerator(Protocol):
    def new(self) -> str: ...


class Repository(Protocol[T]):
    def add(self, entity: T) -> None: ...

    def get(self, entity_id: str) -> T | None: ...

    def list(self) -> Iterable[T]: ...


class EventPublisher(Protocol):
    def publish(self, events: Iterable[object]) -> None: ...


class UnitOfWork(Protocol):
    def __enter__(self) -> UnitOfWork: ...

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

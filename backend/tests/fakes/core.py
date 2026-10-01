from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol


class HasId(Protocol):
    id: object


@dataclass
class FixedClock:
    current: datetime

    def now(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


@dataclass
class VirtualSleeper:
    calls: list[float] = field(default_factory=list)

    def sleep(self, seconds: float) -> None:
        self.calls.append(seconds)


@dataclass
class SequentialIdGenerator:
    prefix: str = "id"
    sequence: int = 0

    def new(self) -> str:
        self.sequence += 1
        return f"{self.prefix}-{self.sequence}"


class InMemoryRepository[T: HasId]:
    def __init__(self) -> None:
        self.items: dict[str, T] = {}

    def add(self, entity: T) -> None:
        self.items[str(entity.id)] = entity

    def get(self, entity_id: str) -> T | None:
        return self.items.get(entity_id)

    def list(self) -> Iterable[T]:
        return tuple(self.items.values())


class InMemoryUnitOfWork:
    def __init__(self, **repositories: object) -> None:
        self.__dict__.update(repositories)
        self.committed = False
        self.rolled_back = False

    def __enter__(self) -> InMemoryUnitOfWork:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if exc is not None:
            self.rollback()

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ResourceGraph:
    strategies: dict[str, Any] = field(default_factory=dict)
    versions: dict[str, Any] = field(default_factory=dict)
    backtests: dict[str, Any] = field(default_factory=dict)
    jobs: dict[str, Any] = field(default_factory=dict)
    documents: dict[str, dict[str, Any]] = field(default_factory=dict)


class ResourceLifecycleStore(Protocol):
    def guard(self) -> AbstractContextManager[None]: ...

    def transaction(self) -> AbstractContextManager[ResourceGraph]: ...
    def add_live_instance(self, instance: dict[str, Any]) -> None: ...

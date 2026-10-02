from __future__ import annotations

from collections.abc import MutableMapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(slots=True)
class LiveTrackingState:
    instances: MutableMapping[str, dict[str, Any]]
    recommendations: MutableMapping[str, list[dict[str, Any]]]
    operations: MutableMapping[str, dict[str, Any]]
    ledger: Any
    audit: Any


class LiveTrackingStore(Protocol):
    def transaction(self) -> AbstractContextManager[LiveTrackingState]: ...

from __future__ import annotations

import random
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from easy_quant.domain.shared.value_objects import ensure_utc


class FactorDataGateway(Protocol):
    def records(self, dataset: str, symbol: str) -> Iterable[Mapping[str, object]]: ...


@dataclass(slots=True)
class FactorContext:
    gateway: FactorDataGateway
    as_of: datetime
    random_seed: int = 0

    def read(self, dataset: str, symbol: str) -> tuple[Mapping[str, object], ...]:
        boundary = ensure_utc(self.as_of)
        return tuple(
            row
            for row in self.gateway.records(dataset, symbol)
            if isinstance(row.get("available_at"), datetime)
            and ensure_utc(row["available_at"]) <= boundary  # type: ignore[arg-type]
        )

    def random(self) -> random.Random:
        return random.Random(self.random_seed)

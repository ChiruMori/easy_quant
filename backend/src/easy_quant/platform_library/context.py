from __future__ import annotations

import random
from collections import OrderedDict
from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol

from easy_quant.domain.shared.value_objects import ensure_utc


class FactorDataGateway(Protocol):
    def records(self, dataset: str, symbol: str) -> Iterable[Mapping[str, object]]: ...


@dataclass(slots=True)
class FactorContext:
    gateway: FactorDataGateway
    as_of: datetime
    random_seed: int = 0

    max_cached_rows: int = 20_000
    _cached_rows: int = field(default=0, init=False)
    _records: OrderedDict[tuple[str, str], tuple[Mapping[str, object], ...]] = field(
        default_factory=OrderedDict, init=False
    )

    def read(self, dataset: str, symbol: str) -> tuple[Mapping[str, object], ...]:
        boundary = ensure_utc(self.as_of)
        key = (dataset, symbol)
        if key not in self._records:
            self._records[key] = tuple(
                copy_record(row) for row in self.gateway.records(dataset, symbol)
            )
            self._cached_rows += len(self._records[key])
        self._records.move_to_end(key)
        while self._cached_rows > self.max_cached_rows and len(self._records) > 1:
            _, expired = self._records.popitem(last=False)
            self._cached_rows -= len(expired)
        return tuple(
            copy_record(row)
            for row in self._records[key]
            if isinstance(row.get("available_at"), datetime)
            and ensure_utc(row["available_at"]) <= boundary  # type: ignore[arg-type]
        )

    def random(self) -> random.Random:
        return random.Random(self.random_seed)


def copy_record(row: Mapping[str, object]) -> dict[str, object]:
    return {
        key: value
        if isinstance(value, (str, int, float, bool, type(None), date, Decimal))
        else deepcopy(value)
        for key, value in row.items()
    }

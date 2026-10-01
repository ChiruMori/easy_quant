from __future__ import annotations

import json
from collections.abc import Iterable, Mapping


class InMemoryMarketDataRepository:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], dict[str, object]] = {}

    def upsert_many(self, dataset_key: str, rows: Iterable[Mapping[str, object]]) -> int:
        count = 0
        for row in rows:
            key = str(row.get("record_key") or row.get("symbol") or count)
            self.records[(dataset_key, key)] = dict(row)
            count += 1
        return count

    def export_json(self) -> str:
        return json.dumps(list(self.records.values()), ensure_ascii=False, default=str)

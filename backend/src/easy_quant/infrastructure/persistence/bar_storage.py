"""压缩日线的批量血缘解析与逻辑读取；应用只有一种物理结构。"""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import Table, select, tuple_
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.orm import Session, registry

from easy_quant.infrastructure.persistence.models.market_data_records import (
    DailyBarModel,
    provenance,
)

compact = cast(Table, DailyBarModel.__table__)
mapper_registry = registry()


class LogicalDailyBar:
    pass


mapper_registry.map_imperatively(
    LogicalDailyBar,
    compact.outerjoin(provenance, compact.c.provenance_id == provenance.c.id),
    primary_key=[compact.c.symbol, compact.c.trading_day],
    exclude_properties=["id", "archive_key", "archive_is_null", "source_key", "adjustment_key"],
)


class BarStorage:
    physical: Any = DailyBarModel
    logical: Any = LogicalDailyBar
    table = compact

    def encode(self, session: Session, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            return rows
        keys = list(
            dict.fromkeys((r["source"], r["adjustment"], r.get("archive_sha256")) for r in rows)
        )
        ids = {}
        for offset in range(0, len(keys), 500):
            batch = keys[offset : offset + 500]
            statement = insert(provenance)
            session.execute(
                statement.on_duplicate_key_update(id=provenance.c.id),
                [dict(source=s, adjustment=a, archive_sha256=h) for s, a, h in batch],
            )
            resolved = session.execute(
                select(
                    provenance.c.id,
                    provenance.c.source,
                    provenance.c.adjustment,
                    provenance.c.archive_sha256,
                ).where(
                    tuple_(
                        provenance.c.source_key,
                        provenance.c.adjustment_key,
                        provenance.c.archive_key,
                        provenance.c.archive_is_null,
                    ).in_(
                        [
                            (
                                s.encode("utf-8"),
                                a.encode("utf-8"),
                                (h or "").encode("utf-8"),
                                int(h is None),
                            )
                            for s, a, h in batch
                        ]
                    )
                )
            )
            for identity, source, adjustment, digest in resolved:
                ids[source, adjustment, digest] = identity
        if set(ids) != set(keys):
            raise RuntimeError("日线来源元数据未完整解析，拒绝写入")
        return [
            {
                **{
                    k: v
                    for k, v in row.items()
                    if k not in {"source", "adjustment", "archive_sha256"}
                },
                "provenance_id": ids[row["source"], row["adjustment"], row.get("archive_sha256")],
            }
            for row in rows
        ]

    def upsert(self):
        statement = insert(self.table)
        return statement.on_duplicate_key_update(
            **{c.name: statement.inserted[c.name] for c in self.table.columns if not c.primary_key}
        )


BAR_STORAGE = BarStorage()

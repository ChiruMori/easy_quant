import gzip
import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session

from easy_quant.infrastructure.persistence.repositories.runtime import (
    SqlAlchemyMarketDataStore,
    streamed_snapshot_chunks,
)
from easy_quant.infrastructure.persistence.snapshot_spool import SnapshotSpool


def test_snapshot_spool_matches_legacy_hash_and_gzip_payload() -> None:
    rows = [
        {"symbol": "000001", "trading_day": "2026-09-01", "source": "测试"},
        {"symbol": "000002", "trading_day": "2026-09-02", "source": "测试"},
    ]
    expected = json.dumps(rows, ensure_ascii=False, sort_keys=True).encode("utf-8")
    with SnapshotSpool() as spool:
        for row in rows:
            spool.append(row)
        assert spool.finish() == hashlib.sha256(expected).hexdigest()
        assert spool.record_count == len(rows)
        assert spool.byte_count == len(expected)
        assert b"".join(spool.chunks()) == expected
        assert gzip.decompress(b"".join(streamed_snapshot_chunks(spool))) == expected


def test_snapshot_spool_rolls_over_without_unbounded_memory() -> None:
    with SnapshotSpool() as spool:
        for index in range(100):
            spool.append({"symbol": f"{index:06d}", "blob": "x" * 100_000})
        spool.finish()
        assert cast(Any, spool._file)._rolled  # noqa: SLF001
        assert spool.record_count == 100


def test_snapshot_scan_uses_primary_for_short_range_and_years() -> None:
    class FakeSession:
        statements: list[Any] = []

        def scalars(self, statement):
            self.statements.append(statement)
            if "DISTINCT" in str(statement):
                return ["000001"]
            return []

        def execute(self, statement):
            self.statements.append(statement)
            return []

    session = FakeSession()
    store = SqlAlchemyMarketDataStore(cast(Session, session))
    assert list(store.iter_snapshot_bars(date(2026, 9, 1), date(2026, 9, 2))) == []
    assert list(store.iter_snapshot_bars(date(2024, 1, 1), date(2026, 9, 2))) == []
    sql = [str(statement.compile(dialect=mysql.dialect())) for statement in session.statements]
    assert "FORCE INDEX (ix_daily_bars_day_symbol)" in sql[0]
    assert "FORCE INDEX (PRIMARY)" in sql[1]
    assert "FORCE INDEX (ix_daily_bars_day_symbol)" in sql[2]
    assert "FORCE INDEX (PRIMARY)" in sql[3]
    assert "daily_bars.symbol IN" in sql[3]


def test_scalar_snapshot_preserves_fields_and_exact_decimal_text():
    row = SimpleNamespace(
        symbol="000001",
        trading_day=date(2026, 9, 1),
        open=Decimal("10.000000"),
        high=Decimal("11.000000"),
        low=Decimal("9.000000"),
        close=Decimal("10.500000"),
        volume=Decimal("100.0000"),
        amount=None,
        available_at=datetime(2026, 9, 1, 7, tzinfo=UTC),
        source="测试",
        adjustment="none",
        archive_sha256="a" * 64,
    )

    class FakeSession:
        def scalars(self, _statement):
            return ["000001"]

        def execute(self, statement):
            assert len(statement.column_descriptions) == 12
            return [row]

    store = SqlAlchemyMarketDataStore(cast(Session, FakeSession()))
    assert list(store.iter_snapshot_bars(row.trading_day, row.trading_day)) == [
        store._snapshot_row(row)
    ]

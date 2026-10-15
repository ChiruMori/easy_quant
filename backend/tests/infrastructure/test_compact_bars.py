from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session

from easy_quant.infrastructure.persistence.bar_storage import BAR_STORAGE, compact, provenance
from easy_quant.infrastructure.persistence.repositories.runtime import (
    SqlAlchemyMarketDataStore,
    bar_coverage_statement,
    runtime_batch_statement,
)


def sql(statement):
    return str(statement.compile(dialect=mysql.dialect()))


class CompactSession:
    def __init__(self):
        self.calls = []
        self.metadata = {}
        self.commits = 0

    def execute(self, statement, values=None):
        self.calls.append((statement, values))
        text = sql(statement)
        if text.startswith("INSERT INTO bar_provenance"):
            assert values is not None
            for row in values:
                key = row["source"], row["adjustment"], row["archive_sha256"]
                self.metadata.setdefault(key, len(self.metadata) + 1)
        if text.startswith("SELECT bar_provenance.id"):
            return [(identity, *key) for key, identity in self.metadata.items()]
        return []

    def commit(self):
        self.commits += 1


def test_exact_provenance_dedup_and_missing_reference_refusal():
    session = CompactSession()
    rows = [
        dict(source=s, adjustment="none", archive_sha256=h)
        for s, h in [
            ("TDX", None),
            ("tdx", None),
            ("TDX", ""),
            ("TDX ", None),
            ("TDX", "Ab"),
            ("TDX", "ab"),
        ]
    ]
    encoded = BAR_STORAGE.encode(cast(Session, session), rows * 100)
    assert len(session.calls) == 2 and len(session.metadata) == 6
    assert len(encoded) == 600
    assert len({r["provenance_id"] for r in encoded}) == 6
    assert all(set(r) == {"provenance_id"} for r in encoded)
    assert not compact.foreign_keys and not provenance.foreign_keys
    session.execute = lambda statement, values=None: []
    with pytest.raises(RuntimeError, match="拒绝写入"):
        BAR_STORAGE.encode(cast(Session, session), rows)


def test_runtime_and_bounds_do_not_join_metadata_but_full_reads_do():
    storage = BAR_STORAGE
    day = date(2026, 10, 1)
    for statement in [
        bar_coverage_statement(include_count=False, Bar=storage.physical),
        runtime_batch_statement(["000001"], day, day, storage.physical),
    ]:
        text = sql(statement)
        assert "bar_provenance" not in text and "FORCE INDEX" in text
    text = sql(
        select(storage.logical).with_hint(
            storage.table, "FORCE INDEX (PRIMARY)", dialect_name="mysql"
        )
    )
    assert "LEFT OUTER JOIN bar_provenance" in text
    assert "daily_bars FORCE INDEX (PRIMARY)" in text


def test_compact_upload_stores_only_ids_and_calendar_in_same_commit():
    session = CompactSession()
    store = SqlAlchemyMarketDataStore(cast(Session, session))
    row = dict(
        symbol="000001",
        trading_day="2026-10-01",
        open="10",
        high="11",
        low="9",
        close="10.5",
        volume="100",
        available_at="2026-10-01T15:00:00+08:00",
        source="tdx",
        adjustment="none",
        archive_sha256=None,
        amount=None,
    )
    store.upsert_bars([row])
    writes = [(sql(s), values) for s, values in session.calls if sql(s).startswith("INSERT")]
    bars = next(values for text, values in writes if text.startswith("INSERT INTO daily_bars"))
    assert bars[0]["provenance_id"] == 1 and "source" not in bars[0]
    assert bars[0]["close"] == Decimal("10.5") and bars[0]["amount"] is None
    assert session.commits == 1
    assert any("INSERT INTO trading_days" in text for text, _ in writes)


def test_snapshot_contract_and_orphans():
    row: Any = SimpleNamespace(
        symbol="000001",
        trading_day=date(2026, 10, 1),
        open=Decimal("10.000000"),
        high=Decimal("11.000000"),
        low=Decimal("9.000000"),
        close=Decimal("10.500000"),
        volume=Decimal("100.0000"),
        amount=None,
        available_at=datetime(2026, 10, 1, 7, tzinfo=UTC),
        source="TDX ",
        adjustment="none",
        archive_sha256="Ab" * 32,
    )
    result = SqlAlchemyMarketDataStore._snapshot_row(row)
    assert result["close"] == "10.500000" and result["source"] == "TDX "
    assert result["archive_sha256"] == "Ab" * 32
    assert result["available_at"] == "2026-10-01T07:00:00+00:00"
    row.source = None
    with pytest.raises(RuntimeError, match="引用缺失"):
        SqlAlchemyMarketDataStore._snapshot_row(row)


@pytest.mark.parametrize("kind", ["history", "daily"])
@pytest.mark.parametrize("missing", [False, True])
def test_compact_imports_keep_metadata_bars_and_checkpoint_transaction(kind, missing):
    from sqlalchemy.orm import sessionmaker

    from easy_quant.infrastructure.imports.tdx import parse_day
    from easy_quant.infrastructure.imports.tdx_daily import parse_daily
    from easy_quant.infrastructure.persistence.repositories.history_import import SqlHistoryStore
    from easy_quant.infrastructure.persistence.repositories.tdx_daily import SqlDailyStore
    from tests.infrastructure.test_tdx_archive import fixture_bytes
    from tests.infrastructure.test_tdx_daily import DAY, daily_members, zip_bytes

    class Transaction(CompactSession):
        committed = False
        rolled_back = False

        def __enter__(self):
            return self

        def __exit__(self, error, *_args):
            self.committed = error is None
            self.rolled_back = error is not None
            return False

        def scalars(self, _statement):
            return []

        def scalar(self, _statement):
            return None

        def execute(self, statement, values=None):
            result = super().execute(statement, values)
            if missing and sql(statement).startswith("SELECT bar_provenance.id"):
                return []
            return result

    session = Transaction()
    factory = cast(sessionmaker[Session], SimpleNamespace(begin=lambda: session))

    def now():
        return datetime(2026, 10, 3, tzinfo=UTC)

    if kind == "history":
        store = SqlHistoryStore(factory, now)

        def operation():
            store.write_stocks("a" * 64, [("000001", parse_day(fixture_bytes(), "000001"))], 100)

        checkpoint = "history_import_stocks"
    else:
        store = SqlDailyStore(factory, now)

        def operation():
            store.write_day(parse_daily(zip_bytes(daily_members()), DAY))

        checkpoint = "tdx_daily_checkpoints"
    if missing:
        with pytest.raises(RuntimeError, match="拒绝写入"):
            operation()
        assert session.rolled_back and not session.committed
        assert not any("INSERT INTO daily_bars" in sql(s) for s, _ in session.calls)
    else:
        operation()
        assert session.committed
        inserts = [(sql(s), values) for s, values in session.calls if sql(s).startswith("INSERT")]
        bars = next(values for text, values in inserts if text.startswith("INSERT INTO daily_bars"))
        assert bars and all("provenance_id" in r and "archive_sha256" not in r for r in bars)
        assert any(f"INSERT INTO {checkpoint}" in text for text, _ in inserts)


def test_canonical_metadata_only_has_compact_columns_and_no_foreign_keys():
    from easy_quant.infrastructure.persistence.base import Base

    assert "bar_provenance" in Base.metadata.tables
    daily = Base.metadata.tables["daily_bars"]
    assert "provenance_id" in daily.c
    assert not {"source", "adjustment", "archive_sha256"} & set(daily.c.keys())
    assert not daily.foreign_keys and not provenance.foreign_keys

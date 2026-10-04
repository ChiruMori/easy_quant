from __future__ import annotations

import importlib.util
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy import Table
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.schema import CreateIndex

from easy_quant.infrastructure.imports.tdx import parse_day
from easy_quant.infrastructure.persistence.models.market_data_records import DailyBarModel
from easy_quant.infrastructure.persistence.repositories.history_import import (
    SqlHistoryStore,
    bar_values,
    bars_upsert,
)
from easy_quant.infrastructure.persistence.repositories.runtime import (
    SqlAlchemyMarketDataStore,
    bar_coverage_statement,
)
from tests.infrastructure.test_tdx_archive import fixture_bytes


def test_mysql_bulk_upsert_preserves_identity_and_price_metadata() -> None:
    rows = [bar_values(bar, "a" * 64) for bar in parse_day(fixture_bytes(), "000001")]
    compiled = bars_upsert().values(rows).compile(dialect=mysql.dialect())
    assert "ON DUPLICATE KEY UPDATE" in str(compiled)
    assert compiled.params["adjustment_m0"] == "none"
    assert compiled.params["source_m0"] == "tdx-official"
    assert compiled.params["archive_sha256_m0"] == "a" * 64
    assert str(compiled.params["close_m0"]) == "10.5"


def test_adjustment_conflict_is_checked_before_any_database_write() -> None:
    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def scalar(self, _query):
            return "000001"

        def scalars(self, _query):
            return []

        def execute(self, _query):
            pytest.fail("口径冲突不得写入")

    class FakeFactory:
        def begin(self):
            return FakeSession()

    store = SqlHistoryStore(
        cast(sessionmaker[Session], FakeFactory()), lambda: datetime(2026, 10, 2, tzinfo=UTC)
    )
    with pytest.raises(ValueError, match="拒绝覆盖"):
        store.write_stocks("a" * 64, [("000001", parse_day(fixture_bytes(), "000001"))], 1)


def test_initial_schema_remains_frozen_before_history_migration() -> None:
    path = Path(__file__).parents[2] / "migrations/versions/0001_initial.py"
    spec = importlib.util.spec_from_file_location("initial_baseline", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    metadata = module.initial_metadata()
    assert "history_import_stocks" not in metadata.tables
    assert "source" not in metadata.tables["daily_bars"].columns
    assert "amount" not in metadata.tables["daily_bars"].columns
    assert not metadata.tables["daily_bars"].indexes


def test_coverage_index_contains_only_symbol_and_date() -> None:
    index = next(
        item
        for item in cast(Table, DailyBarModel.__table__).indexes
        if item.name == "ix_daily_bars_coverage"
    )
    assert [column.name for column in index.columns] == ["symbol", "trading_day"]
    assert "CREATE INDEX ix_daily_bars_coverage" in str(
        CreateIndex(index).compile(dialect=mysql.dialect())
    )
    statement = str(bar_coverage_statement().compile(dialect=mysql.dialect()))
    assert "FORCE INDEX (ix_daily_bars_coverage)" in statement
    assert "daily_bars.open" not in statement


def test_day_range_uses_date_leading_covering_index_without_loading_full_history() -> None:
    index = next(
        item
        for item in cast(Table, DailyBarModel.__table__).indexes
        if item.name == "ix_daily_bars_runtime_day"
    )
    assert [column.name for column in index.columns] == [
        "trading_day",
        "symbol",
        "available_at",
        "open",
        "high",
        "low",
        "close",
    ]

    class FakeSession:
        statement = None

        def scalars(self, statement):
            self.statement = statement
            return []

    session = FakeSession()
    store = SqlAlchemyMarketDataStore(cast(Session, session))
    assert store.list_bars(date(2026, 6, 1), date(2026, 9, 29)) == []
    assert session.statement is not None
    statement = str(session.statement.compile(dialect=mysql.dialect()))
    assert "FORCE INDEX (ix_daily_bars_runtime_day)" in statement
    assert "daily_bars.trading_day >= %s" in statement
    assert "daily_bars.trading_day <= %s" in statement


def test_runtime_covering_index_migration_replaces_old_index_reversibly(monkeypatch) -> None:
    path = Path(__file__).parents[2] / "migrations/versions/0008_runtime_bar_covering_index.py"
    spec = importlib.util.spec_from_file_location("runtime_bar_index", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    actions: list[tuple[str, str]] = []
    monkeypatch.setattr(module.op, "get_context", lambda: SimpleNamespace(as_sql=False))
    monkeypatch.setattr(
        module.op, "create_index", lambda name, *_args: actions.append(("create", name))
    )
    monkeypatch.setattr(
        module.op, "drop_index", lambda name, **_kwargs: actions.append(("drop", name))
    )
    monkeypatch.setattr(module, "_indexes", lambda: {"ix_daily_bars_day_symbol"})
    module.upgrade()
    assert actions == [
        ("create", "ix_daily_bars_runtime_day"),
        ("drop", "ix_daily_bars_day_symbol"),
    ]
    actions.clear()
    monkeypatch.setattr(module, "_indexes", lambda: {"ix_daily_bars_runtime_day"})
    module.downgrade()
    assert actions == [
        ("create", "ix_daily_bars_day_symbol"),
        ("drop", "ix_daily_bars_runtime_day"),
    ]

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from sqlalchemy import Text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session

from easy_quant.infrastructure.persistence.models.market_data_records import JsonMarketRecordModel
from easy_quant.infrastructure.persistence.repositories.runtime import SqlAlchemyMarketDataStore


def test_financial_pages_use_symbol_dataset_cutoff_and_database_limit():
    statements = []

    class FakeSession:
        def scalars(self, statement):
            statements.append(statement)
            return []

        def execute(self, statement):
            statements.append(statement)
            return SimpleNamespace(all=lambda: [("balance-sheets", 2)])

    store = SqlAlchemyMarketDataStore(cast(Session, FakeSession()))
    now = datetime(2026, 9, 29, tzinfo=UTC)
    assert store.record_page("balance-sheets", "000001", now, 2, 10) == []
    assert store.record_counts("000001", now) == {"balance-sheets": 2}
    sql = str(
        statements[0].compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "symbol = '000001'" in sql and "dataset_key = 'balance-sheets'" in sql
    assert "available_at <=" in sql and "LIMIT 10, 10" in sql
    assert isinstance(JsonMarketRecordModel.__table__.c.payload_json.type, Text)


def test_financial_migration_only_expands_existing_record_table(monkeypatch):
    path = Path(__file__).parents[2] / "migrations/versions/0015_financial_records.py"
    spec = importlib.util.spec_from_file_location("financial_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []

    def record(name):
        return lambda *args, **kwargs: calls.append((name, args, kwargs))

    monkeypatch.setattr(
        module,
        "op",
        SimpleNamespace(
            **{
                name: record(name)
                for name in ("alter_column", "add_column", "execute", "create_index")
            }
        ),
    )
    module.upgrade()
    assert {args[0] for name, args, _ in calls if name != "execute" and name != "create_index"} == {
        "market_records"
    }
    assert all(
        "daily_bar" not in str(args) and "FOREIGN KEY" not in str(args) for _, args, _ in calls
    )
    assert calls[-1][1][2] == ["symbol", "dataset_key", "available_at"]


def test_bulk_financial_insert_is_batched_and_duplicate_versions_are_immutable():
    statements = []

    class FakeSession:
        def scalar(self, statement):
            return 0

        def execute(self, statement, rows):
            statements.append((statement, rows))

        def commit(self):
            pass

    store = SqlAlchemyMarketDataStore(cast(Session, FakeSession()))
    rows = [
        {"record_key": str(i), "symbol": f"{i:06d}", "available_at": "2026-09-29T00:00:00+00:00"}
        for i in range(501)
    ]
    store.upsert_records("income-statements", rows)
    assert [len(batch) for _, batch in statements] == [500, 1]
    sql = str(statements[0][0].compile(dialect=mysql.dialect()))
    assert "ON DUPLICATE KEY UPDATE record_key" in sql
    assert "payload_json = VALUES" not in sql

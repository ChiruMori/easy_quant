from datetime import date, timedelta
from typing import cast

from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session

from easy_quant.infrastructure.persistence.repositories.runtime import (
    SqlAlchemyMarketDataStore,
    bar_coverage_statement,
)


def test_global_bounds_do_not_scan_every_bar_to_count_rows():
    sql = str(bar_coverage_statement(include_count=False).compile(dialect=mysql.dialect()))
    assert "count(" not in sql and "min(" in sql and "max(" in sql
    assert "FORCE INDEX (ix_daily_bars_coverage)" in sql


def test_large_upload_checks_keys_and_upserts_in_batches_without_get_merge():
    class BatchSession:
        def __init__(self):
            self.calls = []
            self.commits = 0
            self.metadata = {}

        def execute(self, statement, parameters=None):
            self.calls.append((statement, parameters))
            sql = str(statement.compile(dialect=mysql.dialect()))
            if sql.startswith("INSERT INTO bar_provenance"):
                assert parameters is not None
                for row in parameters:
                    key = row["source"], row["adjustment"], row["archive_sha256"]
                    self.metadata.setdefault(key, len(self.metadata) + 1)
            if sql.startswith("SELECT bar_provenance.id"):
                return [(identity, *key) for key, identity in self.metadata.items()]
            return []

        def get(self, *_args):
            raise AssertionError("禁止逐行查询")

        def merge(self, *_args):
            raise AssertionError("禁止逐行 merge")

        def commit(self):
            self.commits += 1

    session = BatchSession()
    store = SqlAlchemyMarketDataStore(cast(Session, session))
    start = date(2020, 1, 1)
    rows = [
        {
            "symbol": "000001",
            "trading_day": str(start + timedelta(days=i)),
            "open": "10",
            "high": "11",
            "low": "9",
            "close": "10",
            "volume": "100",
            "available_at": f"{start + timedelta(days=i)}T15:00:00+08:00",
        }
        for i in range(1001)
    ]
    assert store.upsert_bars(rows) == 0
    statements = [str(statement.compile(dialect=mysql.dialect())) for statement, _ in session.calls]
    assert sum(sql.startswith("SELECT") for sql in statements) == 5
    assert sum("INSERT INTO daily_bars" in sql for sql in statements) == 3
    assert sum("INSERT INTO trading_days" in sql for sql in statements) == 3
    assert len(session.calls) == 12 and session.commits == 1
    assert all("ON DUPLICATE KEY UPDATE" in sql for sql in statements if sql.startswith("INSERT"))
    session.calls.clear()
    dates = [start + timedelta(days=i) for i in range(1001)]
    store.upsert_trading_days([*dates, dates[0], dates[-1]])
    assert len(session.calls) == 3
    assert sum(len(parameters) for _, parameters in session.calls) == 1001
    assert session.commits == 2

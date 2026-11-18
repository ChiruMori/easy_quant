from contextlib import contextmanager
from types import SimpleNamespace

from sqlalchemy.dialects import mysql

from easy_quant.infrastructure.persistence.factor_statistics import (
    InMemoryFactorStatistics,
    SqlFactorStatistics,
)


def test_duplicate_phase_receipt_is_idempotent_and_distinct_phases_accumulate():
    store = InMemoryFactorStatistics()
    metric = {"technical.ma": {"calls": 2, "elapsed_ns": 1000}}
    store.record("phase-1", metric)
    store.record("phase-1", metric)
    store.record("phase-2", metric)
    assert store.snapshot() == {"technical.ma": {"calls": 4, "elapsed_ns": 2000}}


def test_sql_receipt_and_atomic_increment_share_transaction_and_duplicate_skips():
    statements = []

    class Session:
        affected = 1

        def execute(self, statement):
            statements.append(str(statement.compile(dialect=mysql.dialect())))
            return SimpleNamespace(rowcount=self.affected)

    class Factory:
        @contextmanager
        def begin(self):
            yield Session()

    store = SqlFactorStatistics(Factory())
    store.record("receipt", {"technical.ma": {"calls": 2, "elapsed_ns": 1000}})
    assert "INSERT IGNORE" in statements[0]
    assert "ON DUPLICATE KEY UPDATE" in statements[1]
    assert "factor_statistics.calls +" in statements[1]
    assert "factor_statistics.elapsed_ns +" in statements[1]
    assert all("FOREIGN KEY" not in sql for sql in statements)
    Session.affected = 0
    statements.clear()
    store.record("receipt", {"technical.ma": {"calls": 2, "elapsed_ns": 1000}})
    assert len(statements) == 1
    assert "INSERT IGNORE" in statements[0]

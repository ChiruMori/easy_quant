from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session, sessionmaker

from easy_quant.infrastructure.imports.tdx_daily import parse_daily
from easy_quant.infrastructure.persistence.repositories.tdx_daily import SqlDailyStore
from tests.infrastructure.test_history_transactions import Transaction
from tests.infrastructure.test_tdx_daily import DAY, daily_members, zip_bytes


class Factory:
    def __init__(self, fail=False, conflict=False):
        self.transaction = cast(Any, Transaction(fail=fail))
        if conflict:
            self.transaction.scalar = lambda _query: "600000"

    def begin(self):
        return self.transaction


def test_all_daily_rows_and_success_checkpoint_commit_in_one_transaction() -> None:
    factory = Factory()
    store = SqlDailyStore(
        cast(sessionmaker[Session], factory), lambda: datetime(2026, 10, 2, tzinfo=UTC)
    )
    store.write_day(parse_daily(zip_bytes(daily_members()), DAY))
    assert factory.transaction.committed
    assert factory.transaction.writes == [
        "daily_bars",
        "instruments",
        "trading_days",
        "tdx_daily_checkpoints",
    ]


@pytest.mark.parametrize("conflict", [False, True])
def test_daily_failure_rolls_back_without_success_checkpoint_and_redacts_sql(conflict) -> None:
    factory = Factory(fail=not conflict, conflict=conflict)
    store = SqlDailyStore(
        cast(sessionmaker[Session], factory), lambda: datetime(2026, 10, 2, tzinfo=UTC)
    )
    with pytest.raises((ValueError, RuntimeError)) as error:
        store.write_day(parse_daily(zip_bytes(daily_members()), DAY))
    assert "SECRET" not in str(error.value)
    assert factory.transaction.rolled_back
    assert "tdx_daily_checkpoints" not in factory.transaction.writes


def test_checkpoint_mysql_upsert_keeps_date_as_business_key() -> None:
    queries = []

    class Fake:
        def execute(self, query, values):
            queries.append(query.values(values).compile(dialect=mysql.dialect()))

    store = SqlDailyStore(
        cast(sessionmaker[Session], None), lambda: datetime(2026, 10, 2, tzinfo=UTC)
    )
    store._save_checkpoint(cast(Session, Fake()), DAY, "succeeded", "", "a" * 64, 2)
    assert "ON DUPLICATE KEY UPDATE" in str(queries[0])
    assert queries[0].params["status_m0"] == "succeeded"
    assert queries[0].params["row_count_m0"] == 2


def test_completed_full_import_avoids_rescanning_all_history_for_adjustment() -> None:
    factory = Factory()
    factory.transaction.scalars = lambda _query: ["600000", "000001"]
    factory.transaction.scalar = lambda _query: pytest.fail("已完成全量股票无需重复扫描历史")
    store = SqlDailyStore(
        cast(sessionmaker[Session], factory), lambda: datetime(2026, 10, 2, tzinfo=UTC)
    )
    store.write_day(parse_daily(zip_bytes(daily_members()), DAY))
    assert factory.transaction.committed


def test_lost_database_lock_refuses_new_daily_transaction() -> None:
    factory = Factory()
    store = SqlDailyStore(
        cast(sessionmaker[Session], factory), lambda: datetime(2026, 10, 2, tzinfo=UTC)
    )
    store._lock_session = cast(Session, type("LostLock", (), {"scalar": lambda *_args: 0})())
    with pytest.raises(RuntimeError, match="锁已丢失"):
        store.write_day(parse_daily(zip_bytes(daily_members()), DAY))
    assert not factory.transaction.writes

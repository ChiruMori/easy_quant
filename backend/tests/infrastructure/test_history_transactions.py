from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from easy_quant.infrastructure.imports.tdx import parse_day
from easy_quant.infrastructure.persistence.repositories.history_import import SqlHistoryStore
from tests.infrastructure.test_tdx_archive import fixture_bytes


class Transaction:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.committed = False
        self.rolled_back = False
        self.writes: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, error_type, *_args):
        self.committed = error_type is None
        self.rolled_back = error_type is not None
        return False

    def scalar(self, _query):
        return None

    def scalars(self, _query):
        return []

    def execute(self, query, _rows):
        self.writes.append(query.table.name)
        if self.fail and len(self.writes) == 2:
            raise SQLAlchemyError("SECRET_CONNECTION_DETAIL")


class Factory:
    def __init__(self) -> None:
        self.transactions: list[Transaction] = []

    def begin(self):
        transaction = Transaction(fail=not self.transactions)
        self.transactions.append(transaction)
        return transaction


def test_failed_group_rolls_back_and_checkpoint_cache_updates_only_after_commit() -> None:
    factory = Factory()
    store = SqlHistoryStore(
        cast(sessionmaker[Session], factory), lambda: datetime(2026, 10, 2, tzinfo=UTC)
    )
    digest = "a" * 64
    store._completed[digest] = set()
    stocks = [("000001", parse_day(fixture_bytes(), "000001"))]
    with pytest.raises(RuntimeError) as error:
        store.write_stocks(digest, stocks, 1)
    assert "SECRET" not in str(error.value)
    assert factory.transactions[0].rolled_back
    assert not store.completed(digest, "000001")
    assert not store._known_days
    store.write_stocks(digest, stocks, 1)
    assert factory.transactions[1].committed
    assert factory.transactions[1].writes[-1] == "history_import_stocks"
    assert store.completed(digest, "000001")
    assert len(store._known_days or []) == 2
    store.write_stocks(digest, stocks, 1)
    assert "trading_days" not in factory.transactions[2].writes

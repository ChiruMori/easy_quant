from datetime import date
from typing import cast

import pytest
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session

from easy_quant.application.services.market_data_sync import MarketDataSyncService
from easy_quant.domain.shared.errors import StateConflictError
from easy_quant.infrastructure.persistence.repositories.runtime import (
    InMemoryMarketDataStore,
    SqlAlchemyMarketDataStore,
)


def test_tdx_owned_stock_refuses_public_fetch_and_write_before_changes():
    key = ("000001", "2026-11-11")
    original = {
        "symbol": key[0],
        "trading_day": key[1],
        "source": "tdx-official",
        "adjustment": "none",
        "volume": "105703839",
    }
    store = InMemoryMarketDataStore({key: original}, {}, set())
    with pytest.raises(StateConflictError, match="通达信"):
        MarketDataSyncService({}, store).sync(
            "daily-bars",
            symbols=["000001"],
            start_day=date(2026, 11, 11),
            end_day=date(2026, 11, 11),
        )
    with pytest.raises(StateConflictError, match="通达信"):
        store.upsert_bars([{**original, "source": "tencent", "volume": "1057038"}])
    assert store.daily_bars[key] == original
    assert store.upsert_bars([{**original, "volume": "105703840"}]) == 1


def test_sql_ownership_uses_small_checkpoint_table_before_symbol_range():
    lookups = []

    class FakeSession:
        def scalars(self, statement):
            assert "history_import_stocks" in str(statement)
            return ["000001"]

        def scalar(self, statement):
            compiled = statement.compile(dialect=mysql.dialect())
            lookups.append(compiled)
            assert "LIMIT" in str(compiled) and "WHERE" in str(compiled)
            assert "000008" in compiled.params.values()
            return "000008"

    store = SqlAlchemyMarketDataStore(cast(Session, FakeSession()))
    assert store.tdx_managed_symbols(["000001", "000008"]) == {"000001", "000008"}
    assert len(lookups) == 1

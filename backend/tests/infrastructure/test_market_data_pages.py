from datetime import date
from typing import cast

from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session

from easy_quant.infrastructure.persistence.market_data_pages import DailyBarPageCache
from easy_quant.infrastructure.persistence.repositories.runtime import SqlAlchemyMarketDataStore


def test_daily_pages_hit_miss_and_lru_eviction() -> None:
    class Store:
        def __init__(self) -> None:
            self.calls: list[date] = []

        def list_runtime_bars(self, start_day: date, end_day: date):
            assert start_day == end_day
            self.calls.append(start_day)
            return [{"trading_day": start_day.isoformat()}]

    store = Store()
    cache = DailyBarPageCache(store, max_pages=2)
    first, second, third = (date(2026, 9, day) for day in (1, 2, 3))
    assert len(cache.days((first, second, first))) == 3
    assert store.calls == [first, second]
    cache.day(third)
    cache.day(second)
    assert store.calls == [first, second, third, second]
    assert cache.stats() == {"hits": 1, "misses": 4, "pages": 2}


def test_new_task_cache_sees_revised_data() -> None:
    class Store:
        close = "10"

        def list_runtime_bars(self, start_day: date, end_day: date):
            return [{"close": self.close}]

    store = Store()
    day = date(2026, 9, 1)
    assert DailyBarPageCache(store).day(day)[0]["close"] == "10"
    store.close = "11"
    assert DailyBarPageCache(store).day(day)[0]["close"] == "11"


def test_runtime_query_is_coverable_and_does_not_select_heavy_columns() -> None:
    class FakeSession:
        statement = None

        def execute(self, statement):
            self.statement = statement
            return []

    session = FakeSession()
    store = SqlAlchemyMarketDataStore(cast(Session, session))
    assert store.list_runtime_bars(date(2026, 8, 28), date(2026, 9, 4)) == []
    assert session.statement is not None
    sql = str(session.statement.compile(dialect=mysql.dialect()))
    assert "FORCE INDEX (ix_daily_bars_runtime_day)" in sql
    assert "daily_bars.close" in sql
    assert "daily_bars.available_at" in sql
    assert "daily_bars.volume" not in sql
    assert "daily_bars.archive_sha256" not in sql

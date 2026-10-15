from datetime import date, timedelta
from typing import cast

from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session

from easy_quant.infrastructure.persistence.market_data_pages import DailyBarPageCache
from easy_quant.infrastructure.persistence.repositories.runtime import (
    SqlAlchemyMarketDataStore,
    runtime_batch_statement,
    runtime_symbols_statement,
)


def test_daily_pages_hit_miss_and_lru_eviction() -> None:
    class Store:
        def __init__(self) -> None:
            self.calls: list[tuple[date, date]] = []

        def list_runtime_bars(self, start_day: date, end_day: date):
            self.calls.append((start_day, end_day))
            return [
                {"trading_day": (start_day + timedelta(days=offset)).isoformat()}
                for offset in range((end_day - start_day).days + 1)
            ]

    store = Store()
    cache = DailyBarPageCache(store, max_pages=2)
    first, second, third = (date(2026, 9, day) for day in (1, 2, 3))
    assert len(cache.days((first, second, first))) == 3
    assert store.calls == [(first, second)]
    cache.day(third)
    cache.day(second)
    assert store.calls == [(first, second), (date(2026, 9, 1), date(2026, 9, 30))]
    cache.day(date(2026, 10, 1))
    cache.day(second)
    cache.day(date(2026, 11, 1))
    cache.day(date(2026, 10, 2))
    assert store.calls[-1] == (date(2026, 10, 1), date(2026, 10, 31))
    assert cache.stats() == {"hits": 3, "misses": 6, "pages": 2, "queries": 5}


def test_new_task_cache_sees_revised_data() -> None:
    class Store:
        close = "10"

        def list_runtime_bars(self, start_day: date, end_day: date):
            return [{"close": self.close, "trading_day": str(start_day)}]

    store = Store()
    day = date(2026, 9, 1)
    assert DailyBarPageCache(store).day(day)[0]["close"] == "10"
    store.close = "11"
    assert DailyBarPageCache(store).day(day)[0]["close"] == "11"


def test_many_days_are_fetched_in_one_window_and_retained_in_one_month() -> None:
    calls: list[tuple[date, date]] = []

    class Store:
        def list_runtime_bars(self, start_day: date, end_day: date):
            calls.append((start_day, end_day))
            return [
                {"trading_day": (start_day + timedelta(days=offset)).isoformat()}
                for offset in range((end_day - start_day).days + 1)
            ]

    start = date(2026, 9, 1)
    days = [start + timedelta(days=index) for index in range(30)]
    cache = DailyBarPageCache(Store())
    assert len(cache.days(days)) == 30
    assert calls == [(days[0], days[-1])]
    assert cache.stats() == {"hits": 0, "misses": 30, "pages": 1, "queries": 1}


def test_prefetch_keeps_previously_cached_pages_when_lru_evicts_them() -> None:
    class Store:
        def list_runtime_bars(self, start_day: date, end_day: date):
            return [
                {"trading_day": (start_day + timedelta(days=offset)).isoformat()}
                for offset in range((end_day - start_day).days + 1)
            ]

    start = date(2026, 9, 1)
    dates = [start + timedelta(days=index) for index in range(6)]
    cache = DailyBarPageCache(Store(), max_pages=1)
    cache.day(dates[-1])
    dates.append(date(2026, 10, 5))
    assert [row["trading_day"] for row in cache.days(dates)] == [day.isoformat() for day in dates]
    assert cache.stats() == {"hits": 6, "misses": 2, "pages": 1, "queries": 2}


def test_empty_days_are_cached_and_month_prefetch_does_not_leak_future_days():
    class Store:
        calls = 0

        def list_runtime_bars(self, first, last):
            self.calls += 1
            return [{"symbol": "000001", "trading_day": "2026-09-30", "close": "99"}]

    store = Store()
    cache = DailyBarPageCache(store)
    assert cache.day(date(2026, 9, 1)) == ()
    assert cache.day(date(2026, 9, 2)) == ()
    assert store.calls == 1


def test_sparse_month_requests_do_not_fetch_intervening_years():
    class Store:
        calls = []

        def list_runtime_bars(self, first, last):
            self.calls.append((first, last))
            return []

    store = Store()
    cache = DailyBarPageCache(store)
    assert cache.days([date(2000, 1, 1), date(2026, 9, 1)]) == []
    assert store.calls == [
        (date(2000, 1, 1), date(2000, 1, 1)),
        (date(2026, 9, 1), date(2026, 9, 1)),
    ]


def test_runtime_query_discovers_symbols_then_reads_primary_key_ranges() -> None:
    start, end = date(2026, 8, 28), date(2026, 9, 4)
    discovery = str(runtime_symbols_statement(start, end).compile(dialect=mysql.dialect()))
    assert "FORCE INDEX (ix_daily_bars_day_symbol)" in discovery
    assert "DISTINCT" in discovery
    assert "daily_bars.open" not in discovery
    batch = str(runtime_batch_statement(["000001"], start, end).compile(dialect=mysql.dialect()))
    assert "FORCE INDEX (PRIMARY)" in batch
    assert "daily_bars.symbol IN" in batch
    assert "daily_bars.close" in batch
    assert "daily_bars.available_at" in batch
    assert "daily_bars.volume" not in batch
    assert "daily_bars.archive_sha256" not in batch


def test_runtime_store_batches_symbols_and_sorts_rows_by_day() -> None:
    class FakeSession:
        def scalars(self, _statement):
            return ["000002", "000001"]

        def execute(self, _statement):
            return [
                ("000002", date(2026, 9, 2), date(2026, 9, 2), 2, 2, 2, 2),
                ("000001", date(2026, 9, 1), date(2026, 9, 1), 1, 1, 1, 1),
            ]

    store = SqlAlchemyMarketDataStore(cast(Session, FakeSession()))
    rows = store.list_runtime_bars(date(2026, 9, 1), date(2026, 9, 2))
    assert [row["symbol"] for row in rows] == ["000001", "000002"]


def test_backtest_runtime_iterator_reads_one_month_at_a_time(monkeypatch) -> None:
    store = SqlAlchemyMarketDataStore(cast(Session, object()))
    calls: list[tuple[date, date]] = []

    def list_rows(start_day: date, end_day: date):
        calls.append((start_day, end_day))
        return [{"trading_day": start_day.isoformat()}]

    monkeypatch.setattr(store, "list_runtime_bars", list_rows)
    rows = list(store.iter_runtime_bars(date(2026, 8, 30), date(2026, 10, 2)))
    assert [row["trading_day"] for row in rows] == [
        "2026-08-30",
        "2026-09-01",
        "2026-10-01",
    ]
    assert calls == [
        (date(2026, 8, 30), date(2026, 8, 31)),
        (date(2026, 9, 1), date(2026, 9, 30)),
        (date(2026, 10, 1), date(2026, 10, 2)),
    ]

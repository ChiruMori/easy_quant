"""单任务区段缓存：批量窗口按需读；单日缺失预取整月，按月块做 LRU。"""

from __future__ import annotations

from calendar import monthrange
from collections import OrderedDict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any


@dataclass
class MonthPage:
    ranges: list[tuple[date, date]] = field(default_factory=list)
    rows: dict[date, tuple[dict[str, Any], ...]] = field(default_factory=dict)

    def covers(self, day: date) -> bool:
        return any(first <= day <= last for first, last in self.ranges)


class DailyBarPageCache:
    def __init__(self, store: Any, *, max_pages: int = 2) -> None:
        if max_pages < 1:
            raise ValueError("max_pages 必须为正数")
        self._store = store
        self._max_pages = max_pages
        self._pages: OrderedDict[date, MonthPage] = OrderedDict()
        self._hits = self._misses = self._queries = 0

    @staticmethod
    def _month(day: date) -> date:
        return day.replace(day=1)

    def _cached(self, day: date) -> tuple[dict[str, Any], ...] | None:
        key = self._month(day)
        page = self._pages.get(key)
        if page is None or not page.covers(day):
            return None
        self._pages.move_to_end(key)
        return page.rows.get(day, ())

    def _read(self, first: date, last: date) -> dict[date, tuple[dict[str, Any], ...]]:
        self._queries += 1
        fetched: dict[date, list[dict[str, Any]]] = {}
        for row in self._store.list_runtime_bars(first, last):
            day = date.fromisoformat(str(row["trading_day"]))
            if first <= day <= last:
                fetched.setdefault(day, []).append(row)
        cursor = self._month(first)
        while cursor <= last:
            end = date(cursor.year, cursor.month, monthrange(cursor.year, cursor.month)[1])
            page = self._pages.setdefault(cursor, MonthPage())
            begin, stop = max(first, cursor), min(last, end)
            page.ranges.append((begin, stop))
            for offset in range((stop - begin).days + 1):
                day = begin + timedelta(days=offset)
                page.rows[day] = tuple(fetched.get(day, []))
            self._pages.move_to_end(cursor)
            if len(self._pages) > self._max_pages:
                self._pages.popitem(last=False)
            cursor = end + timedelta(days=1)
        return {day: tuple(rows) for day, rows in fetched.items()}

    def day(self, day: date) -> tuple[dict[str, Any], ...]:
        cached = self._cached(day)
        if cached is not None:
            self._hits += 1
            return cached
        self._misses += 1
        first = self._month(day)
        last = date(day.year, day.month, monthrange(day.year, day.month)[1])
        return self._read(first, last).get(day, ())

    def days(self, trading_days: Iterable[date]) -> list[dict[str, Any]]:
        dates = list(trading_days)
        result = []
        for offset in range(0, len(dates), 48):
            window = dates[offset : offset + 48]
            cached_before = {}
            for day in window:
                cached = self._cached(day)
                if cached is not None:
                    cached_before[day] = cached
            missing = sorted(set(window) - cached_before.keys())
            fetched = {}
            ranges: list[list[date]] = []
            for day in missing:
                if (
                    not ranges
                    or (day.year * 12 + day.month)
                    - (ranges[-1][-1].year * 12 + ranges[-1][-1].month)
                    > 1
                ):
                    ranges.append([day])
                else:
                    ranges[-1].append(day)
            for group in ranges:
                fetched.update(self._read(group[0], group[-1]))
            seen = set()
            for day in window:
                if day in cached_before or day in seen:
                    self._hits += 1
                else:
                    self._misses += 1
                seen.add(day)
                # 预取可能淘汰早期月份，当前请求使用独立的临时返回值。
                result.extend(cached_before.get(day, fetched.get(day, ())))
                month = self._month(day)
                if month in self._pages:
                    self._pages.move_to_end(month)
        return result

    def stats(self) -> dict[str, int]:
        return {
            "hits": self._hits,
            "misses": self._misses,
            "pages": len(self._pages),
            "queries": self._queries,
        }

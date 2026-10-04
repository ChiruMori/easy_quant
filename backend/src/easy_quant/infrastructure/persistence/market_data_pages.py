"""单任务日线页缓存；因子重叠请求只读取同一个交易日页一次。"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable
from datetime import date
from typing import Any


class DailyBarPageCache:
    def __init__(self, store: Any, *, max_pages: int = 12) -> None:
        if max_pages < 1:
            raise ValueError("max_pages 必须为正数")
        self._store = store
        self._max_pages = max_pages
        self._pages: OrderedDict[date, tuple[dict[str, Any], ...]] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def _remember(self, day: date, rows: tuple[dict[str, Any], ...]) -> None:
        self._pages[day] = rows
        self._pages.move_to_end(day)
        if len(self._pages) > self._max_pages:
            self._pages.popitem(last=False)

    def day(self, day: date) -> tuple[dict[str, Any], ...]:
        if day in self._pages:
            self._hits += 1
            self._pages.move_to_end(day)
            return self._pages[day]
        self._misses += 1
        rows = tuple(self._store.list_runtime_bars(day, day))
        self._remember(day, rows)
        return rows

    def days(self, trading_days: Iterable[date]) -> list[dict[str, Any]]:
        dates = list(trading_days)
        result: list[dict[str, Any]] = []
        # 批量范围读取可跨多页；LRU 仍只留 max_pages 页。
        fetch_days = max(12, self._max_pages * 4)
        for offset in range(0, len(dates), fetch_days):
            window = dates[offset : offset + fetch_days]
            cached_before = {day: self._pages[day] for day in window if day in self._pages}
            missing = sorted({day for day in window if day not in self._pages})
            fetched: dict[date, list[dict[str, Any]]] = {
                **{day: list(rows) for day, rows in cached_before.items()},
                **{day: [] for day in missing},
            }
            if missing:
                for row in self._store.list_runtime_bars(missing[0], missing[-1]):
                    row_day = date.fromisoformat(str(row["trading_day"]))
                    if row_day in fetched:
                        fetched[row_day].append(row)
            for day in window:
                if day in self._pages:
                    result.extend(self.day(day))
                else:
                    if day in cached_before:
                        self._hits += 1
                    else:
                        self._misses += 1
                    rows = tuple(fetched[day])
                    self._remember(day, rows)
                    result.extend(rows)
        return result

    def stats(self) -> dict[str, int]:
        return {"hits": self._hits, "misses": self._misses, "pages": len(self._pages)}

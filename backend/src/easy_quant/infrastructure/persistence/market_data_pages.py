"""单任务日线页缓存；因子重叠请求只读取同一个交易日页一次。"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from functools import lru_cache
from typing import Any


class DailyBarPageCache:
    def __init__(self, store: Any, *, max_pages: int = 12) -> None:
        if max_pages < 1:
            raise ValueError("max_pages 必须为正数")

        @lru_cache(maxsize=max_pages)
        def load_day(day: date) -> tuple[dict[str, Any], ...]:
            return tuple(store.list_runtime_bars(day, day))

        self._load_day = load_day

    def day(self, day: date) -> tuple[dict[str, Any], ...]:
        return self._load_day(day)

    def days(self, trading_days: Iterable[date]) -> list[dict[str, Any]]:
        return [row for day in trading_days for row in self.day(day)]

    def stats(self) -> dict[str, int]:
        info = self._load_day.cache_info()
        return {"hits": info.hits, "misses": info.misses, "pages": info.currsize}

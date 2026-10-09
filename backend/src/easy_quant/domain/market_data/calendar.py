from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo


class FreshnessStatus(StrEnum):
    UPDATED = "updated"
    STALE = "stale"
    NOT_UPDATED = "not_updated"


@dataclass(frozen=True, slots=True)
class MarketDataFreshness:
    status: FreshnessStatus
    previous_trading_day: date
    recommended_end_day: date


class TradingCalendar:
    def __init__(self, trading_days: set[date] | None = None) -> None:
        self._trading_days = trading_days

    def is_trading_day(self, day: date) -> bool:
        if self._trading_days is not None:
            return day in self._trading_days
        return day.weekday() < 5

    def previous_trading_day(self, day: date) -> date:
        if self._trading_days is not None:
            known = [candidate for candidate in self._trading_days if candidate < day]
            if known:
                return max(known)
        candidate = day - timedelta(days=1)
        while candidate.weekday() >= 5:
            candidate -= timedelta(days=1)
        return candidate

    def freshness(
        self,
        *,
        first_day: date | None,
        last_day: date | None,
        now: datetime,
        close_time: time = time(22, 0),
    ) -> MarketDataFreshness:
        local_now = now.astimezone(ZoneInfo("Asia/Shanghai"))
        previous = self.previous_trading_day(local_now.date())
        recommended = (
            local_now.date()
            if self.is_trading_day(local_now.date()) and local_now.time() >= close_time
            else previous
        )
        if last_day is not None and last_day >= recommended:
            status = FreshnessStatus.UPDATED
        elif first_day is not None and last_day is not None and (last_day - first_day).days >= 90:
            status = FreshnessStatus.STALE
        else:
            status = FreshnessStatus.NOT_UPDATED
        return MarketDataFreshness(status, previous, recommended)

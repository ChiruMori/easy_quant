from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from easy_quant.domain.market_data.history import HistoryBar
from easy_quant.domain.shared.errors import DomainError


@dataclass(frozen=True)
class HolidayCalendar:
    years: frozenset[int]
    holidays: frozenset[date]
    sha256: str

    def closed(self, day: date) -> bool:
        return day.weekday() >= 5 or (day.year in self.years and day in self.holidays)


@dataclass(frozen=True)
class DailyArchive:
    day: date
    sha256: str
    bars: tuple[HistoryBar, ...]
    suspended: int = 0


@dataclass(frozen=True)
class DayCheckpoint:
    status: str
    sha256: str | None = None


class DailyFeed(Protocol):
    def calendar(self) -> HolidayCalendar: ...

    def fetch(self, day: date) -> DailyArchive | None: ...


class DailyStore(Protocol):
    def exclusive(self) -> AbstractContextManager[None]: ...

    def baseline(self) -> date | None: ...

    def checkpoints(self) -> dict[date, DayCheckpoint]: ...

    def write_day(self, archive: DailyArchive) -> None: ...

    def mark(self, day: date, status: str, reason: str, digest: str | None = None) -> None: ...


@dataclass
class DailyUpdateResult:
    start_day: str = ""
    end_day: str = ""
    imported_days: int = 0
    imported_rows: int = 0
    unchanged_days: int = 0
    closed_days: int = 0
    unresolved: list[dict[str, str]] = field(default_factory=list)


class TdxDailyUpdateService:
    def __init__(self, feed: DailyFeed, store: DailyStore, now: Callable[[], datetime]) -> None:
        self.feed, self.store, self.now = feed, store, now

    def update(
        self,
        *,
        start_day: date | None = None,
        end_day: date | None = None,
        progress: Callable[[DailyUpdateResult], None] = lambda _result: None,
    ) -> DailyUpdateResult:
        current = self.now()
        if current.tzinfo is None:
            raise ValueError("更新时点必须包含时区")
        local = current.astimezone(ZoneInfo("Asia/Shanghai"))
        cutoff = local.date() - timedelta(days=int(local.time() < time(18)))
        end = end_day or cutoff
        if end > cutoff:
            raise ValueError("只能更新已到盘后发布时间的日期（Asia/Shanghai 18:00）")
        with self.store.exclusive():
            checkpoints = self.store.checkpoints()
            baseline = self.store.baseline()
            if baseline is None:
                raise ValueError("请先完成无失败的通达信全量历史导入")
            if start_day is None:
                latest = max(checkpoints, default=baseline)
                first = baseline + timedelta(days=1)
                cursor = first
                for recorded in sorted(day for day in checkpoints if first <= day <= end):
                    if recorded != cursor:
                        break
                    cursor += timedelta(days=1)
                start = min(max(first, latest - timedelta(days=6)), cursor)
                pending = [
                    day
                    for day, state in checkpoints.items()
                    if state.status in {"pending", "failed"} and day <= end
                ]
                if pending:
                    start = min(start, min(pending))
            else:
                start = start_day
            if start > end:
                if start_day is not None:
                    raise ValueError("开始日期不能晚于结束日期")
                return DailyUpdateResult(str(start), str(end))
            if (end - start).days >= 90:
                raise ValueError("单次最多更新 90 个自然日；请显式分段补数或重新全量导入")
            result = DailyUpdateResult(str(start), str(end))
            calendar = self.feed.calendar()
            day = start
            while day <= end:
                prior = checkpoints.get(day)
                try:
                    if calendar.closed(day):
                        # 已有成功行情不能被后续日历修订抹去。
                        if prior is None or prior.status != "succeeded":
                            self.store.mark(day, "closed", "官方休市日或周末", calendar.sha256)
                        result.closed_days += 1
                    else:
                        archive = self.feed.fetch(day)
                        if archive is None:
                            if prior is not None and prior.status == "succeeded":
                                result.unchanged_days += 1
                            else:
                                self.store.mark(day, "pending", "官方日线包尚未发布（404）")
                                result.unresolved.append({"day": str(day), "status": "pending"})
                        else:
                            if archive.day != day or not archive.bars:
                                raise ValueError("日线包日期错误或没有有效 A 股行情")
                            for bar in archive.bars:
                                if bar.trading_day != day:
                                    raise ValueError("行情日期与下载日期不一致")
                                bar.validate()
                            if (
                                prior
                                and prior.status == "succeeded"
                                and prior.sha256 == archive.sha256
                            ):
                                result.unchanged_days += 1
                            else:
                                self.store.write_day(archive)
                                result.imported_days += 1
                                result.imported_rows += len(archive.bars)
                except (ValueError, RuntimeError, DomainError) as error:
                    # 检查点写入失败让整个任务失败；下一次重新从未确认日期开始。
                    self.store.mark(day, "failed", str(error))
                    result.unresolved.append(
                        {"day": str(day), "status": "failed", "reason": str(error)}
                    )
                progress(result)
                day += timedelta(days=1)
            return result

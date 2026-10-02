from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import cast

import pytest

from easy_quant.application.services.tdx_incremental import DayCheckpoint, TdxDailyUpdateService
from easy_quant.domain.scheduling.entities import Job
from easy_quant.infrastructure.imports.tdx_daily import parse_calendar, parse_daily
from easy_quant.worker.handlers.market_data import register_market_data_handlers
from easy_quant.worker.registry import JobHandlerRegistry
from tests.infrastructure.test_tdx_daily import DAY, calendar_bytes, daily_members, zip_bytes


class Store:
    def __init__(self):
        self.states = {}
        self.bars = {}
        self.fail = False
        self.baseline_day: date | None = date(2026, 9, 29)

    def exclusive(self):
        return nullcontext()

    def baseline(self):
        return self.baseline_day

    def checkpoints(self):
        return dict(self.states)

    def mark(self, day, status, reason, digest=None):
        self.states[day] = DayCheckpoint(status, digest)

    def write_day(self, archive):
        if self.fail:
            raise RuntimeError("模拟事务回滚")
        for bar in archive.bars:
            self.bars[bar.symbol, bar.trading_day] = bar
        self.states[archive.day] = DayCheckpoint("succeeded", archive.sha256)


class Feed:
    def __init__(self):
        self.archive = parse_daily(zip_bytes(daily_members()), DAY)
        self.requested = []

    def calendar(self):
        return parse_calendar(calendar_bytes())

    def fetch(self, day):
        self.requested.append(day)
        return self.archive if day == DAY else None


def service(feed=None, store=None, now=datetime(2026, 10, 2, 12, tzinfo=UTC)):
    return TdxDailyUpdateService(feed or Feed(), store or Store(), lambda: now)


def test_replay_is_idempotent_and_source_revision_updates_same_business_keys() -> None:
    feed, store = Feed(), Store()
    updater = service(feed, store)
    first = updater.update(start_day=DAY, end_day=DAY)
    assert first.imported_rows == 2 and len(store.bars) == 2
    assert updater.update(start_day=DAY, end_day=DAY).unchanged_days == 1
    feed.archive = replace(feed.archive, sha256="b" * 64)
    assert updater.update(start_day=DAY, end_day=DAY).imported_rows == 2
    assert len(store.bars) == 2 and store.states[DAY].sha256 == "b" * 64


def test_failed_day_retries_even_when_later_days_already_succeeded() -> None:
    feed, store = Feed(), Store()
    store.states[DAY] = DayCheckpoint("failed")
    store.states[date(2026, 10, 12)] = DayCheckpoint("succeeded", "a" * 64)
    result = service(feed, store, datetime(2026, 10, 12, 12, tzinfo=UTC)).update()
    assert feed.requested[0] == DAY
    assert result.imported_days == 1 and store.states[DAY].status == "succeeded"


def test_unrecorded_gap_is_recovered_after_explicit_later_range() -> None:
    feed, store = Feed(), Store()
    store.states[date(2026, 10, 12)] = DayCheckpoint("succeeded", "a" * 64)
    result = service(feed, store, datetime(2026, 10, 12, 12, tzinfo=UTC)).update()
    assert result.start_day == "2026-09-30" and feed.requested[0] == DAY


def test_missing_nonholiday_day_remains_pending_and_does_not_hide_behind_success() -> None:
    feed, store = Feed(), Store()
    day = date(2026, 9, 29)
    result = service(feed, store).update(start_day=day, end_day=DAY)
    assert result.unresolved == [{"day": str(day), "status": "pending"}]
    assert store.states[day].status == "pending" and store.states[DAY].status == "succeeded"
    assert service(feed, store).update().start_day == str(day)


def test_holiday_weekend_and_local_cutoff_do_not_download_incomplete_session() -> None:
    feed, store = Feed(), Store()
    now = datetime(2026, 10, 2, 9, 59, tzinfo=UTC)
    result = service(feed, store, now).update()
    assert result.end_day == "2026-10-01"
    assert result.closed_days == 1 and feed.requested == [DAY]
    with pytest.raises(ValueError, match="盘后"):
        service(feed, store, now).update(end_day=date(2026, 10, 2))


def test_transaction_failure_has_no_bars_and_recovers() -> None:
    feed, store = Feed(), Store()
    store.fail = True
    assert service(feed, store).update(start_day=DAY, end_day=DAY).unresolved
    assert not store.bars and store.states[DAY].status == "failed"
    store.fail = False
    assert service(feed, store).update(start_day=DAY, end_day=DAY).imported_days == 1


def test_archive_day_mismatch_and_unknown_calendar_year_never_mark_success() -> None:
    feed, store = Feed(), Store()
    feed.archive = replace(feed.archive, day=date(2026, 9, 29))
    assert service(feed, store).update(start_day=DAY, end_day=DAY).unresolved
    assert not store.bars
    future_day = date(2027, 10, 1)
    result = service(feed, store, datetime(2027, 10, 1, 12, tzinfo=UTC)).update(
        start_day=future_day, end_day=future_day
    )
    assert result.unresolved[0]["status"] == "pending" and future_day in feed.requested


def test_missing_full_baseline_and_excessive_range_fail_before_network() -> None:
    feed = Feed()
    store = Store()
    with pytest.raises(ValueError, match="90"):
        service(feed, store).update(start_day=date(2026, 1, 1), end_day=DAY)
    store.baseline_day = None
    with pytest.raises(ValueError, match="全量"):
        service(feed, store).update()
    assert not feed.requested


def test_worker_reports_unresolved_dates_as_failure_and_can_retry() -> None:
    feed, store = Feed(), Store()
    registry = JobHandlerRegistry()
    register_market_data_handlers(registry, SimpleNamespace(tdx_daily=service(feed, store)))
    handler = registry.get("tdx-daily-update")
    with pytest.raises(RuntimeError, match="未解决"):
        handler(
            cast(Job, SimpleNamespace(payload={"start_day": "2026-09-29", "end_day": "2026-09-30"}))
        )
    result = handler(
        cast(Job, SimpleNamespace(payload={"start_day": "2026-09-30", "end_day": "2026-09-30"}))
    )
    assert result is not None and result["status"] == "succeeded"

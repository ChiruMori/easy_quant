from datetime import date, timedelta
from typing import Any, cast

import pytest

from easy_quant.application.ports.jobs import JobContinuation
from easy_quant.application.services.acquisition import AcquisitionFailed
from easy_quant.domain.scheduling.entities import Job, JobStatus
from easy_quant.worker.handlers.collection import units
from easy_quant.worker.handlers.market_data import register_market_data_handlers
from easy_quant.worker.registry import JobHandlerRegistry
from easy_quant.worker.runner import Worker
from tests.fakes.core import FixedClock, VirtualSleeper
from tests.fakes.platform import make_test_container


def setup_collection():
    container = make_test_container()
    calls = []

    class Sync:
        def sync(self, dataset, **kwargs):
            calls.append((dataset, kwargs))
            return {}

    container.data_sync = cast(Any, Sync())
    container.market_data.upsert_instruments([{"symbol": f"{index:06d}"} for index in range(41)])
    registry = JobHandlerRegistry()
    register_market_data_handlers(registry, container)
    job = Job(
        "night",
        "market-data-collection",
        "night",
        {"end_day": "2026-09-28"},
        container.authentication.clock.now(),
    )
    return container, calls, registry, job


def test_old_completed_reports_do_not_refetch_when_thirty_days_expire():
    container, calls, registry, job = setup_collection()
    handler = registry.get(job.job_type)
    handler(job)
    work = units(date(2026, 9, 28))
    index = next(
        i
        for i, unit in enumerate(work)
        if unit == {"dataset": "balance-sheets", "period": "2024-12-31"}
    )
    job.payload["collection"]["unit"] = index
    checkpoint = {
        "completed_at": (container.authentication.clock.now() - timedelta(days=90)).isoformat()
    }
    container.collection_checkpoints["balance-sheets:2024-12-31"] = checkpoint.copy()
    handler(job)
    assert job.payload["collection"]["unit"] == index + 1
    assert container.collection_checkpoints["balance-sheets:2024-12-31"] == checkpoint
    assert len(calls) == 1


def test_daily_collection_fills_internal_gap_even_with_current_last_bar():
    container, calls, registry, job = setup_collection()
    handler = registry.get(job.job_type)
    handler(job)
    state = job.payload["collection"]
    state["bar_day"] = "2026-09-28"
    state["unit"] = next(
        i for i, unit in enumerate(units(date(2026, 9, 28))) if unit["dataset"] == "daily-bars"
    )
    container.market_data.instruments.clear()
    container.market_data.upsert_instruments([{"symbol": "000001"}])
    container.market_data.upsert_trading_days([date(2026, 9, day) for day in (24, 25, 28)])
    for day in (24, 28):
        container.market_data.daily_bars[("000001", f"2026-09-{day}")] = {
            "symbol": "000001",
            "trading_day": f"2026-09-{day}",
        }
    handler(job)
    assert calls[-1][0] == "daily-bars"
    assert calls[-1][1]["start_day"] == date(2026, 9, 25)
    assert calls[-1][1]["end_day"] == date(2026, 9, 28)
    assert container.collection_checkpoints["daily-bars:000001"]["missing_checked"] == {
        "2026-09-25": "2026-09-28"
    }


def test_nightly_keeps_one_resumable_job_and_never_fans_out():
    container, calls, registry, job = setup_collection()
    container.jobs.enqueue(job)
    worker = Worker("w", container.jobs, registry, container.authentication.clock, VirtualSleeper())
    assert worker.run_once()
    stored = container.jobs.get(job.id)
    assert stored.status == JobStatus.QUEUED
    assert stored.payload["collection"]["unit"] == 1
    assert stored.result_summary["collection"] is True
    assert len(container.jobs.list_all()) == 1
    assert not container.state.acquisitions
    assert calls[0][0] == "trading-calendar"


def test_bulk_pages_resume_without_repeating_previous_page_and_checkpoint_history():
    container, _, registry, job = setup_collection()
    seen = []

    class Bulk:
        def page(self, dataset, period, page, symbols):
            seen.append((dataset, period, page, symbols))
            return (
                [
                    {
                        "schema_version": "financial-v1",
                        "symbol": "000001",
                        "report_period": period,
                        "total_assets": str(page),
                    }
                ],
                2,
                600,
            )

    container.financial_bulk = Bulk()
    handler = registry.get(job.job_type)
    handler(job)
    handler(job)
    assert isinstance(handler(job), JobContinuation)
    assert job.payload["collection"]["page"] == 2
    handler(job)
    assert [row[2] for row in seen] == [1, 2]
    assert len(seen[0][3]) == 41
    assert job.payload["collection"]["unit"] == 3
    assert "balance-sheets:2026-06-30" in container.collection_checkpoints
    assert not container.jobs.list_all()


def test_failed_unit_backs_off_three_times_then_other_datasets_continue():
    container, _, registry, job = setup_collection()

    class Broken:
        def sync(self, *args, **kwargs):
            raise ValueError("temporary")

    container.data_sync = cast(Any, Broken())
    handler = registry.get(job.job_type)
    first = handler(job)
    assert isinstance(first, JobContinuation)
    assert first.resume_at == container.authentication.clock.now() + timedelta(minutes=5)
    handler(job)
    handler(job)
    state = job.payload["collection"]
    assert state["unit"] == 1 and len(state["failed"]) == 1
    state["unit"] = len(units(date(2026, 9, 28)))
    with pytest.raises(AcquisitionFailed):
        handler(job)
    assert not container.jobs.list_all()


def test_legacy_fanout_jobs_do_not_make_requests():
    _, calls, registry, job = setup_collection()
    job.payload = {"task_id": "nightly:2026-11-01:income-statements:old"}
    result = registry.get("market-data-acquisition")(job)
    assert isinstance(result, dict) and result["status"] == "skipped"
    assert calls == []


def test_active_collection_is_reused_for_new_schedule_trigger():
    container, _, _, job = setup_collection()
    container.jobs.enqueue(job)
    duplicate = Job("other", job.job_type, "other", {}, job.available_at)
    assert container.jobs.enqueue(duplicate).id == job.id
    assert len(container.jobs.list_all()) == 1


def test_daily_failure_does_not_skip_remaining_stocks_or_create_child_jobs():
    container, _, registry, job = setup_collection()
    handler = registry.get(job.job_type)
    handler(job)
    state = job.payload["collection"]
    state["unit"] = next(
        i for i, unit in enumerate(units(date(2026, 9, 28))) if unit["dataset"] == "daily-bars"
    )
    calls = []

    class Sync:
        def sync(self, dataset, **kwargs):
            calls.append(kwargs["symbols"])
            if kwargs["symbols"] == ["000000"]:
                raise ValueError("temporary")
            return {"record_count": 1}

    container.data_sync = cast(Any, Sync())
    for _ in range(4):
        handler(job)
    assert calls == [["000000"], ["000000"], ["000000"], ["000001"]]
    assert state["last_symbol"] == "000001"
    assert state["failed"][0]["symbol"] == "000000"
    assert state["records"] == 1
    assert not container.jobs.list_all()


def test_repeated_provider_page_cannot_complete_the_dataset():
    from easy_quant.infrastructure.data_sources.financial_bulk import BulkPage

    container, _, registry, job = setup_collection()
    handler = registry.get(job.job_type)
    handler(job)
    handler(job)
    row = {"schema_version": "financial-v1", "symbol": "000001", "report_period": "2026-06-30"}

    class Bulk:
        def page(self, *args):
            return BulkPage([row], 2, 600, "repeated-page", "000001", "000001")

    container.financial_bulk = Bulk()
    handler(job)
    handler(job)
    assert job.payload["collection"]["page"] == 2
    assert job.payload["collection"]["retries"] == 1
    assert "balance-sheets:2026-06-30" not in container.collection_checkpoints


def test_cross_day_collection_does_not_discard_current_snapshot_as_future_data():
    from zoneinfo import ZoneInfo

    container, calls, registry, job = setup_collection()
    handler = registry.get(job.job_type)
    handler(job)
    state = job.payload["collection"]
    state["unit"] = next(
        i for i, unit in enumerate(units(date(2026, 9, 28))) if unit["dataset"] == "market-values"
    )
    clock = cast(FixedClock, container.authentication.clock)
    clock.advance(timedelta(days=2))
    handler(job)
    assert calls[-1][1]["end_day"] == clock.now().astimezone(ZoneInfo("Asia/Shanghai")).date()
    assert state["day"] == "2026-09-28"


def test_business_upgrade_resets_legacy_stock_cursor_then_resumes_pages_without_stock_requests():
    container, calls, registry, job = setup_collection()
    handler = registry.get(job.job_type)
    handler(job)
    state = job.payload["collection"]
    work = units(date(2026, 9, 28))
    index = next(i for i, unit in enumerate(work) if unit["dataset"] == "business-compositions")
    state.update(unit=index, last_symbol="000025", retries=2)
    seen = []

    class Bulk:
        def page(self, dataset, period, page, symbols):
            seen.append((dataset, period, page))
            return (
                [
                    {
                        "schema_version": "financial-v1",
                        "symbol": "000001",
                        "report_period": period,
                        "item_name": f"项目{page}",
                        "category": "2",
                    }
                ],
                2,
                501,
            )

    container.financial_bulk = Bulk()
    # 旧的逐股/全范围检查点不能误认为新报告期已批量完成。
    container.collection_checkpoints["business-compositions:"] = {
        "completed_at": container.authentication.clock.now().isoformat()
    }
    handler(job)
    assert state["page"] == 2 and state["last_symbol"] == ""
    assert f"business-compositions:{work[index]['period']}" not in container.collection_checkpoints
    handler(job)
    assert [item[2] for item in seen] == [1, 2]
    assert state["unit"] == index + 1
    assert f"business-compositions:{work[index]['period']}" in container.collection_checkpoints
    assert len(calls) == 1  # 仅初始化时的交易日历，未调用逐股同步。
    assert not container.jobs.list_all()


@pytest.mark.parametrize(
    ("period", "age", "should_fetch"),
    [("2024-12-31", 400, False), ("2026-06-30", 29, False), ("2026-06-30", 31, True)],
)
def test_business_refresh_uses_period_checkpoints_and_thirty_day_recent_ttl(
    period, age, should_fetch
):
    container, _, registry, job = setup_collection()
    handler = registry.get(job.job_type)
    handler(job)
    state = job.payload["collection"]
    state["unit"] = units(date(2026, 9, 28)).index(
        {"dataset": "business-compositions", "period": period}
    )
    container.collection_checkpoints[f"business-compositions:{period}"] = {
        "completed_at": (container.authentication.clock.now() - timedelta(days=age)).isoformat()
    }
    seen = []

    class Bulk:
        def page(self, *args):
            seen.append(args)
            return [], 0, 0

    container.financial_bulk = Bulk()
    handler(job)
    assert bool(seen) == should_fetch


def test_failed_business_page_does_not_checkpoint_and_continues_other_report_periods():
    container, _, registry, job = setup_collection()
    handler = registry.get(job.job_type)
    handler(job)
    state = job.payload["collection"]
    work = units(date(2026, 9, 28))
    index = next(i for i, unit in enumerate(work) if unit["dataset"] == "business-compositions")
    state["unit"] = index

    class Broken:
        def page(self, *args):
            raise ValueError("unavailable")

    container.financial_bulk = Broken()
    for _ in range(3):
        handler(job)
    assert state["unit"] == index + 1
    assert f"business-compositions:{work[index]['period']}" not in container.collection_checkpoints
    assert state["failed"][0]["period"] == work[index]["period"]

import json
from datetime import timedelta
from typing import Any, cast

import httpx
import pytest

from easy_quant.application.services.acquisition import (
    AcquisitionFailed,
    AcquisitionService,
    ExponentialRetry,
)
from easy_quant.application.services.data_schedules import ensure_data_schedule
from easy_quant.application.services.market_data_sync import (
    validate_securities_response,
)
from easy_quant.domain.market_data.entities import SemanticRequest
from easy_quant.domain.scheduling.entities import Job, JobStatus
from easy_quant.infrastructure.data_sources.eastmoney.adapters import EastMoneySource
from easy_quant.infrastructure.data_sources.eastmoney.client import EastMoneyClient
from easy_quant.worker.handlers.market_data import register_market_data_handlers
from easy_quant.worker.registry import JobHandlerRegistry
from easy_quant.worker.runner import Worker
from tests.application.test_acquisition_service import MemoryCache, Source
from tests.fakes.core import FixedClock, VirtualSleeper
from tests.fakes.platform import make_test_container


@pytest.mark.parametrize("dataset", ["securities", "market-values"])
def test_stock_list_reads_all_pages_when_provider_caps_page_size(dataset):
    seen = []
    rows = [
        {"f12": code, "f14": "测试证券"}
        for code in ["000001", "000002", "600001", "688001", "920001"]
    ]

    def handler(request):
        seen.append(request.url.params)
        page = int(request.url.params["pn"])
        return httpx.Response(
            200, json={"data": {"total": 5, "diff": rows[(page - 1) * 2 : page * 2]}}
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = json.loads(
            EastMoneySource(EastMoneyClient(client)).fetch(SemanticRequest(dataset, {}, "v1"))[0]
        )
    assert result["data"]["diff"] == rows and len(seen) == 3
    assert all(row["pz"] == "100" and row["fid"] == "f12" and "t:81" in row["fs"] for row in seen)


@pytest.mark.parametrize("broken", ["duplicate", "empty", "changed"])
def test_partial_and_unstable_stock_pages_fail(broken):
    def handler(request):
        page = int(request.url.params["pn"])
        batch = [{"f12": "000001", "f14": "测试"}]
        if page == 2 and broken == "empty":
            batch = []
        if page == 2 and broken == "changed":
            batch = [{"f12": "000002", "f14": "测试"}]
        return httpx.Response(
            200,
            json={"data": {"total": 3 if page == 2 and broken == "changed" else 2, "diff": batch}},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client, pytest.raises(ValueError):
        EastMoneySource(EastMoneyClient(client)).fetch(SemanticRequest("securities", {}, "v1"))


def test_truncated_securities_fail_before_cache_and_switch_source(fixed_now):
    bad = Source(
        "eastmoney",
        payload=json.dumps(
            {"data": {"total": 6000, "diff": [{"f12": "000001", "f14": "测试"}]}}
        ).encode(),
    )
    good = Source("akshare", payload=json.dumps([{"code": "000001", "name": "测试"}]).encode())
    cache = MemoryCache()
    service = AcquisitionService(
        [bad, good],
        cache,
        FixedClock(fixed_now),
        VirtualSleeper(),
        ExponentialRetry(1, 0),
        shuffle=lambda _: None,
        validate=validate_securities_response,
    )
    result, attempts = service.acquire_with_attempts(SemanticRequest("securities", {}, "v1"))
    assert result.source_key == "akshare" and cache.value == result
    assert [row.status for row in attempts] == ["failed", "succeeded"]


def test_default_automatic_plan_is_enabled_immediately_and_preserves_existing_choices(fixed_now):
    schedules = {}
    ensure_data_schedule(schedules, fixed_now, "22:15")
    plan = schedules["schedule-market-data-nightly"]
    assert plan["enabled"] is True and plan["next_run_at"] == fixed_now.isoformat()
    assert plan["schedule_expression"] == "15 22 * * 1-5"
    ensure_data_schedule(schedules, fixed_now + timedelta(days=1), "21:00")
    assert len(schedules) == 1 and plan == schedules["schedule-market-data-nightly"]
    custom = {
        "custom": {
            "task_type": "market-data-nightly",
            "enabled": False,
            "schedule_expression": "0 23 * * *",
        }
    }
    before = json.dumps(custom)
    ensure_data_schedule(custom, fixed_now, "22:00")
    assert json.dumps(custom) == before


def test_failed_catalog_refresh_keeps_known_stocks_and_enqueues_financial_jobs_idempotently():
    container = make_test_container()
    container.market_data.upsert_instruments(
        [{"symbol": "000001", "status": "active"}, {"symbol": "000002", "status": "suspended"}]
    )

    class Sync:
        def sync(self, dataset, **kwargs):
            if dataset in {"securities", "trading-status", "trading-calendar"}:
                raise ValueError("来源暂时失败")

    container.data_sync = cast(Any, Sync())
    registry = JobHandlerRegistry()
    register_market_data_handlers(registry, container)
    job = Job("night", "market-data-nightly", "night", {}, container.authentication.clock.now())
    for _ in range(2):
        with pytest.raises(AcquisitionFailed) as caught:
            registry.get("market-data-nightly")(job)
        failures = caught.value.details["failed_datasets"]
        assert isinstance(failures, list) and len(failures) == 3
    jobs = container.jobs.list_all()
    assert len(jobs) == 12
    assert sum(row.payload["dataset_key"] == "balance-sheets" for row in jobs) == 1
    assert next(row for row in jobs if row.payload["dataset_key"] == "daily-bars").payload[
        "symbols"
    ] == ["000001"]
    assert container.market_data.get_instrument("000002")["status"] == "suspended"


def test_acquisition_retries_automatically_with_delay_and_stops_after_three_attempts():
    container = make_test_container()

    class Sync:
        def sync(self, *args, **kwargs):
            raise RuntimeError("来源暂时失败")

    container.data_sync = cast(Any, Sync())
    container.state.acquisitions["task"] = {"id": "task", "status": "queued"}
    registry = JobHandlerRegistry()
    register_market_data_handlers(registry, container)
    clock = cast(FixedClock, container.authentication.clock)
    job = Job(
        "j",
        "market-data-acquisition",
        "task",
        {"task_id": "task", "dataset_key": "balance-sheets"},
        clock.now(),
    )
    container.jobs.enqueue(job)
    worker = Worker("w", container.jobs, registry, clock, VirtualSleeper())
    for attempt in range(1, 4):
        before = clock.now()
        assert worker.run_once()
        saved = container.jobs.get("j")
        assert saved.attempt_count == attempt
        if attempt < 3:
            assert saved.status == JobStatus.QUEUED and saved.available_at == before + timedelta(
                minutes=5 * attempt
            )
            assert container.state.acquisitions["task"]["status"] == "queued"
            assert not worker.run_once()
            clock.current = saved.available_at
        else:
            assert saved.status == JobStatus.FAILED
            assert container.state.acquisitions["task"]["status"] == "failed"
            assert not worker.run_once()

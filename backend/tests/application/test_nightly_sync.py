from typing import Any, cast

from easy_quant.domain.scheduling.entities import Job
from easy_quant.worker.handlers.market_data import register_market_data_handlers
from easy_quant.worker.registry import JobHandlerRegistry
from tests.fakes.platform import make_test_container


def test_nightly_batches_are_idempotent_and_respect_source_settings():
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
    now = container.authentication.clock.now()
    job = Job("night", "market-data-nightly", "night", {}, now)
    first = registry.get("market-data-nightly")(job)
    second = registry.get("market-data-nightly")(job)
    assert first is not None and second is not None
    assert first["child_jobs"] == second["child_jobs"]
    tasks = list(container.state.acquisitions.values())
    bars = [task for task in tasks if task["dataset_key"] == "daily-bars"]
    assert [len(task["symbols"]) for task in bars] == [20, 20, 1]
    assert all(task["end_day"] == "2026-09-28" for task in tasks)
    assert len(tasks) == 9
    assert all("source_keys" in kwargs for _, kwargs in calls)
    assert [dataset for dataset, _ in calls[:3]] == [
        "trading-calendar",
        "securities",
        "trading-status",
    ]
    assert calls[2][1]["confirmation_source_keys"] == {"akshare", "eastmoney", "tencent"}


def test_nightly_does_not_schedule_daily_bars_for_suspended_symbols():
    container = make_test_container()

    class Sync:
        def sync(self, *_args, **_kwargs):
            return {}

    container.data_sync = cast(Any, Sync())
    container.market_data.upsert_instruments(
        [
            {"symbol": "600293", "status": "suspended"},
            {"symbol": "000001", "status": "active"},
        ]
    )
    registry = JobHandlerRegistry()
    register_market_data_handlers(registry, container)
    registry.get("market-data-nightly")(
        Job("night", "market-data-nightly", "night", {}, container.authentication.clock.now())
    )
    bars = [
        task
        for task in container.state.acquisitions.values()
        if task["dataset_key"] == "daily-bars"
    ]
    assert [task["symbols"] for task in bars] == [["000001"]]


def test_nightly_automatically_resumes_and_enqueues_catchup_bars():
    from datetime import date

    from easy_quant.application.services.market_data_sync import MarketDataSyncService
    from tests.application.test_market_data_sync import FakeAcquisition, _traded_bar

    container = make_test_container()
    container.market_data.upsert_instruments(
        [
            {"symbol": "600293", "status": "suspended"},
            {"symbol": "688496", "status": "suspended"},
        ]
    )
    daily = FakeAcquisition([_traded_bar()])
    container.data_sync = MarketDataSyncService(
        {
            "securities": FakeAcquisition([{"code": "600293"}, {"code": "688496"}]),
            "trading-calendar": FakeAcquisition([{"trade_date": "2026-09-30"}]),
            "trading-status": FakeAcquisition(
                [{"symbol": "688496", "status": "suspended", "as_of_day": "2026-09-30"}]
            ),
            "daily-bars": daily,
        },
        container.market_data,
    )
    registry = JobHandlerRegistry()
    register_market_data_handlers(registry, container)
    result = registry.get("market-data-nightly")(
        Job(
            "night",
            "market-data-nightly",
            "night",
            {"end_day": date(2026, 9, 30).isoformat()},
            container.authentication.clock.now(),
        )
    )
    bars = [
        task
        for task in container.state.acquisitions.values()
        if task["dataset_key"] == "daily-bars"
    ]
    assert [task["symbols"] for task in bars] == [["600293"]]
    assert result is not None
    trading_status = result["trading_status"]
    assert isinstance(trading_status, dict)
    assert trading_status["resumed_symbols"] == ["600293"]
    assert len(daily.requests) == 1
    assert daily.requests[0].parameters["symbol"] == "600293"

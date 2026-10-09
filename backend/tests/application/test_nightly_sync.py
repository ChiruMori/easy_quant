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
    assert all(task["end_day"] == "2026-09-29" for task in tasks)
    assert len(tasks) == 9
    assert all("source_keys" in kwargs for _, kwargs in calls)

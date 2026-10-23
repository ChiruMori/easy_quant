from datetime import date
from typing import Any, cast

import pytest

from easy_quant.domain.market_data.indices import INDEX_CATALOG
from easy_quant.domain.scheduling.entities import Job
from easy_quant.domain.shared.errors import ValidationError
from easy_quant.worker.handlers.market_data import register_market_data_handlers
from easy_quant.worker.registry import JobHandlerRegistry
from tests.fakes.platform import make_test_container


def setup_sync(fail_symbol=None):
    container = make_test_container()
    calls = []

    class Sync:
        def sync(self, dataset, **kwargs):
            calls.append((dataset, kwargs))
            if kwargs["symbols"] == [fail_symbol]:
                raise ValidationError("来源未发布")
            return {"record_count": 2, "attempts": []}

    container.data_sync = cast(Any, Sync())
    registry = JobHandlerRegistry()
    register_market_data_handlers(registry, container)
    return container, calls, registry.get("index-daily-update")


def test_index_schedule_uses_publish_boundary_all_indices_and_existing_coverage():
    container, calls, handler = setup_sync()
    container.market_data.upsert_bars(
        [
            {
                "symbol": "sh000300",
                "trading_day": date(2026, 9, 25),
                "open": "10",
                "high": "10",
                "low": "10",
                "close": "10",
                "volume": "1",
                "adjustment": "none",
            }
        ]
    )
    result = handler(
        Job("indices", "index-daily-update", "indices", {}, container.authentication.clock.now())
    )
    assert result is not None and result["record_count"] == 14
    assert [kwargs["symbols"][0] for _, kwargs in calls] == list(INDEX_CATALOG)
    assert all(
        dataset == "daily-bars" and kwargs["end_day"] == date(2026, 9, 29)
        for dataset, kwargs in calls
    )
    assert next(kwargs for _, kwargs in calls if kwargs["symbols"] == ["sh000300"])[
        "start_day"
    ] == date(2026, 9, 25)
    assert calls[0][1]["start_day"] == date(2016, 1, 1)
    assert all(
        kwargs["force"] and kwargs["source_keys"] == {"akshare", "eastmoney", "tencent"}
        for _, kwargs in calls
    )


def test_index_partial_failure_keeps_other_results_and_can_retry_same_task():
    container, calls, handler = setup_sync("sh000300")
    job = Job(
        "indices",
        "index-daily-update",
        "indices",
        {"symbols": ["sh000300", "sz399006"], "start_day": "2026-09-01", "end_day": "2026-09-28"},
        container.authentication.clock.now(),
    )
    with pytest.raises(ValidationError) as failure:
        handler(job)
    assert failure.value.details["record_count"] == 2
    assert len(calls) == 2
    assert container.state.acquisitions["index:indices:sh000300"]["status"] == "failed"
    assert container.state.acquisitions["index:indices:sz399006"]["status"] == "succeeded"

    class RecoveredSync:
        def sync(self, *_args, **_kwargs):
            return {"record_count": 2}

    container.data_sync = cast(Any, RecoveredSync())
    result = handler(job)
    assert result is not None and result["record_count"] == 4
    assert len(container.state.acquisitions) == 2


@pytest.mark.parametrize(
    "payload",
    [
        {"symbols": []},
        {"symbols": ["000001"]},
        {"symbols": ["sh000300", "sh000300"]},
        {"start_day": "bad"},
        {"start_day": "2026-10-01", "end_day": "2026-09-28"},
    ],
)
def test_invalid_index_configuration_has_no_side_effect(payload):
    container, calls, handler = setup_sync()
    with pytest.raises(ValidationError):
        handler(
            Job(
                "indices",
                "index-daily-update",
                "indices",
                payload,
                container.authentication.clock.now(),
            )
        )
    assert not calls and not container.state.acquisitions


@pytest.mark.parametrize(
    "hour,expected", [(14, "2026-09-28"), (15, "2026-09-29"), (21, "2026-09-29")]
)
def test_index_close_boundary_independent_of_stock_publication(hour, expected):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from tests.fakes.core import FixedClock

    container, calls, handler = setup_sync()
    container.authentication.clock = FixedClock(
        datetime(2026, 9, 29, hour, tzinfo=ZoneInfo("Asia/Shanghai"))
    )
    handler(
        Job("boundary", "index-daily-update", "boundary", {}, container.authentication.clock.now())
    )
    assert all(kwargs["end_day"].isoformat() == expected for _, kwargs in calls)

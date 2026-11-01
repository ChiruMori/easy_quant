from datetime import timedelta
from typing import cast

import httpx
import pytest

from easy_quant.domain.scheduling.entities import Job
from easy_quant.infrastructure.data_sources.request_budget import (
    CollectionCancelled,
    RequestBudget,
    before_data_request,
    request_budget,
)
from easy_quant.worker.registry import JobHandlerRegistry
from easy_quant.worker.runner import Worker
from tests.fakes.core import FixedClock
from tests.fakes.platform import make_test_container


def test_every_http_attempt_is_spaced_including_pages_and_retries(fixed_now):
    clock = FixedClock(fixed_now)
    checks, sent = [], []

    class Sleeper:
        def sleep(self, seconds):
            clock.advance(timedelta(seconds=seconds))

    budget = RequestBudget(clock, Sleeper(), lambda: checks.append(clock.now()))

    def handle(request):
        sent.append(clock.now())
        return httpx.Response(429 if len(sent) == 2 else 200)

    with (
        request_budget(budget),
        httpx.Client(
            transport=httpx.MockTransport(handle), event_hooks={"request": [before_data_request]}
        ) as client,
    ):
        for _ in range(3):
            client.get("https://fixture.invalid/page")
    assert sent == [fixed_now, fixed_now + timedelta(seconds=5), fixed_now + timedelta(seconds=10)]
    assert len(checks) >= 3


def test_deleting_running_job_prevents_the_next_request():
    container = make_test_container()
    registry = JobHandlerRegistry()
    sent = []

    def handle(job):
        def send(request):
            sent.append(request.url.path)
            container.jobs.items.pop(job.id)
            return httpx.Response(200)

        with httpx.Client(
            transport=httpx.MockTransport(send), event_hooks={"request": [before_data_request]}
        ) as client:
            client.get("https://fixture.invalid/first")
            client.get("https://fixture.invalid/must-not-send")
        return {}

    class Sleeper:
        def sleep(self, seconds):
            cast(FixedClock, container.authentication.clock).advance(timedelta(seconds=seconds))

    registry.register("market-data-collection", handle)
    container.jobs.enqueue(
        Job("a", "market-data-collection", "a", {}, container.authentication.clock.now())
    )
    assert Worker(
        "w", container.jobs, registry, container.authentication.clock, Sleeper()
    ).run_once()
    assert sent == ["/first"] and not container.jobs.list_all()


def test_cancel_signal_is_not_swallowed_by_source_exception_handlers():
    def cancelled():
        raise CollectionCancelled()

    with pytest.raises(CollectionCancelled):
        RequestBudget(None, None, cancelled).before_request()

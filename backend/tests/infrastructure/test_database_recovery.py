import logging
from typing import Any, cast

import pymysql
import pytest
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from easy_quant.application.ports.storage_errors import StorageFailure
from easy_quant.application.services.acquisition import AcquisitionService
from easy_quant.domain.market_data.entities import SemanticRequest
from easy_quant.domain.scheduling.entities import Job, JobStatus
from easy_quant.infrastructure.persistence.recovery import run_idempotent
from easy_quant.infrastructure.persistence.repositories.raw_cache import (
    SqlAlchemyCompressedRawCache,
)
from easy_quant.worker.registry import JobHandlerRegistry
from easy_quant.worker.runner import Worker
from tests.application.test_acquisition_service import Source
from tests.application.test_nightly_sync import setup_collection
from tests.fakes.core import FixedClock, VirtualSleeper
from tests.fakes.platform import make_test_container


def db_error(number):
    return OperationalError(
        "PRIVATE_SQL_SENTINEL",
        {"password": "PRIVATE_PARAMETER_SENTINEL"},
        pymysql.OperationalError(number, "PRIVATE_DRIVER_MESSAGE_SENTINEL"),
        connection_invalidated=number == 2013,
    )


class RecoveringSession:
    def __init__(self, failures):
        self.failures = list(failures)
        self.statements, self.events = [], []

    def execute(self, statement):
        self.statements.append(statement)
        self.events.append("execute")
        if self.failures:
            raise db_error(self.failures.pop(0))

    def commit(self):
        self.events.append("commit")

    def rollback(self):
        self.events.append("rollback")

    def invalidate(self):
        self.events.append("invalidate")


@pytest.mark.parametrize(
    ("number", "reset"),
    [(2013, "invalidate"), (2006, "invalidate"), (1213, "rollback"), (1205, "rollback")],
)
def test_cache_recovers_locally_without_refetching_or_source_backoff(
    fixed_now, number, reset, caplog
):
    session = RecoveringSession([number])
    cache = SqlAlchemyCompressedRawCache(cast(Session, session))
    source, sleeper = Source("eastmoney"), VirtualSleeper()
    service = AcquisitionService([source], cache, FixedClock(fixed_now), sleeper)
    with caplog.at_level(logging.WARNING):
        result = service.acquire(SemanticRequest("securities", {}, "v1"), force=True)
    assert result.source_key == "eastmoney" and source.calls == 1
    assert session.events == ["execute", reset, "execute", "commit"]
    assert sleeper.calls == []
    sql = str(session.statements[0].compile(dialect=mysql.dialect()))
    assert sql.startswith("INSERT") and "ON DUPLICATE KEY UPDATE" in sql
    assert "数据库局部恢复" in caplog.text
    assert "PRIVATE_" not in caplog.text


@pytest.mark.parametrize(
    ("number", "category"),
    [
        (1045, "database_configuration"),
        (1049, "database_configuration"),
        (1146, "database_schema"),
        (1054, "database_schema"),
        (2003, "database_unavailable"),
        (1406, "database_failed"),
    ],
)
def test_permanent_database_errors_do_not_retry_or_leak_sql(number, category, caplog):
    session = RecoveringSession([number])
    with pytest.raises(StorageFailure) as caught:
        run_idempotent(session, "fixture.write", lambda: session.execute("fixture"))
    assert caught.value.code == category
    assert session.events == ["execute", "rollback"]
    assert caught.value.details["database_code"] == number
    assert "数据库操作失败" in caplog.text and "OperationalError" in caplog.text
    assert "PRIVATE_" not in caplog.text and "PRIVATE_" not in str(caught.value)


def test_second_disconnect_fails_immediately_with_safe_traceback(fixed_now, caplog):
    session = RecoveringSession([2013, 2013, 2013])
    source = Source("eastmoney")
    cache = SqlAlchemyCompressedRawCache(cast(Session, session))
    service = AcquisitionService([source], cache, FixedClock(fixed_now), VirtualSleeper())
    with pytest.raises(StorageFailure) as caught:
        service.acquire(SemanticRequest("securities", {}, "v1"), force=True)
    assert caught.value.code == "database_connection_lost"
    assert len(session.statements) == 2 and source.calls == 1
    assert "raw_cache.py" in caplog.text and "2013" in caplog.text
    assert "PRIVATE_" not in caplog.text


def test_collection_database_error_fails_job_instead_of_queuing_source_retry(caplog):
    container, calls, registry, job = setup_collection()

    class Sync:
        def sync(self, *args, **kwargs):
            raise db_error(1045)

    container.data_sync = cast(Any, Sync())
    container.jobs.enqueue(job)
    worker = Worker("w", container.jobs, registry, container.authentication.clock, VirtualSleeper())
    worker.run_once()
    saved = container.jobs.get(job.id)
    assert saved.status == JobStatus.FAILED
    assert saved.error_summary["code"] == "database_configuration"
    assert "retry_at" not in saved.error_summary
    assert saved.payload["collection"]["retries"] == 0
    assert saved.payload["collection"]["unit"] == 0
    assert "来源失败" not in caplog.text and "数据库操作失败" in caplog.text
    assert "PRIVATE_" not in caplog.text


def test_failed_finish_is_logged_without_claiming_result_was_saved(caplog):
    container = make_test_container()

    def fail_save(*args):
        raise db_error(2013)

    container.jobs.finish_claim = fail_save
    registry = JobHandlerRegistry()
    registry.register("demo", lambda job: {})
    container.jobs.enqueue(Job("a", "demo", "a", {}, container.authentication.clock.now()))
    with pytest.raises(StorageFailure):
        Worker(
            "w", container.jobs, registry, container.authentication.clock, VirtualSleeper()
        ).run_once()
    assert "result_not_saved" in caplog.text and "job.finish_claim" in caplog.text
    assert "PRIVATE_" not in caplog.text


def test_cache_factory_closes_read_session_before_source_io(fixed_now):
    events = []

    class CacheSession:
        def __enter__(self):
            events.append("open")
            return self

        def __exit__(self, *args):
            events.append("close")

        def get(self, *args):
            return None

        def execute(self, statement):
            events.append("write")

        def commit(self):
            events.append("commit")

    class HttpSource(Source):
        def fetch(self, request):
            assert events == ["open", "close"]
            events.append("fetch")
            return super().fetch(request)

    cache = SqlAlchemyCompressedRawCache(cast(Session, None), cast(Any, CacheSession))
    AcquisitionService(
        [HttpSource("eastmoney")], cache, FixedClock(fixed_now), VirtualSleeper()
    ).acquire(SemanticRequest("securities", {}, "v1"))
    assert events == ["open", "close", "fetch", "open", "write", "commit", "close"]


def test_coordinator_database_failure_exits_with_safe_log(caplog):
    container = make_test_container()

    def fail_claim(*args):
        raise db_error(1045)

    container.jobs.claim_due = fail_claim
    with pytest.raises(SystemExit) as caught:
        Worker(
            "w",
            container.jobs,
            JobHandlerRegistry(),
            container.authentication.clock,
            VirtualSleeper(),
        ).run_forever()
    assert caught.value.code == 1
    assert "无法领取或持久化任务" in caplog.text
    assert "PRIVATE_" not in caplog.text


def test_database_failure_inside_http_request_hook_is_not_a_source_retry():
    import httpx

    from easy_quant.infrastructure.data_sources.request_budget import before_data_request

    container = make_test_container()
    calls = []

    class HttpSource(Source):
        def fetch(self, request):
            self.calls += 1
            with httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: (calls.append(request), httpx.Response(200))[1]
                ),
                event_hooks={"request": [before_data_request]},
            ) as client:
                client.get("https://fixture.invalid/must-not-send")
            return b"[]", "application/json"

    def fail_check(*args):
        raise db_error(2013)

    container.jobs.is_claim_current = fail_check
    source = HttpSource("eastmoney")
    from tests.application.test_acquisition_service import MemoryCache

    service = AcquisitionService(
        [source], MemoryCache(), container.authentication.clock, VirtualSleeper()
    )
    registry = JobHandlerRegistry()

    def handle(job):
        service.acquire(SemanticRequest("securities", {}, "v1"), force=True)
        return {}

    registry.register("market-data-collection", handle)
    container.jobs.enqueue(
        Job("a", "market-data-collection", "a", {}, container.authentication.clock.now())
    )
    Worker(
        "w", container.jobs, registry, container.authentication.clock, VirtualSleeper()
    ).run_once()
    saved = container.jobs.get("a")
    assert saved.status == JobStatus.FAILED
    assert saved.error_summary["code"] == "database_connection_lost"
    assert source.calls == 1 and not calls

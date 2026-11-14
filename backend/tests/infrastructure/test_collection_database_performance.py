from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import cast

import httpx
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session

from easy_quant.application.ports.jobs import JobContinuation
from easy_quant.domain.scheduling.entities import Job
from easy_quant.infrastructure.data_sources.request_budget import before_data_request
from easy_quant.infrastructure.persistence.repositories.jobs import SqlAlchemyJobRepository
from easy_quant.infrastructure.persistence.repositories.runtime import SqlAlchemyMarketDataStore
from easy_quant.worker.handlers.collection import units
from easy_quant.worker.registry import JobHandlerRegistry
from easy_quant.worker.runner import Worker
from tests.application.test_nightly_sync import setup_collection
from tests.fakes.core import FixedClock
from tests.fakes.platform import make_test_container


def test_securities_upsert_uses_500_row_writes_without_per_stock_selects():
    statements = []

    class SessionFake:
        def execute(self, statement, rows):
            statements.append((statement, rows))

        def commit(self):
            pass

        def expire_all(self):
            pass

    store = SqlAlchemyMarketDataStore(cast(Session, SessionFake()))
    store.upsert_instruments([{"symbol": f"{i:06d}", "exchange": "测试"} for i in range(5574)])
    assert len(statements) == 12 and len(statements[-1][1]) == 74
    sql = str(statements[0][0].compile(dialect=mysql.dialect()))
    assert "ON DUPLICATE KEY UPDATE" in sql and "CASE WHEN" in sql
    assert "status" in sql


def test_financial_versions_project_only_metadata_and_current_period():
    statements = []

    class SessionFake:
        def execute(self, statement):
            statements.append(statement)
            return [
                SimpleNamespace(
                    _mapping={
                        "symbol": "000001",
                        "record_key": "hash",
                        "available_at": now,
                        "source": "eastmoney",
                        "report_period": "2026-09-30",
                        "statement_scope": "合并",
                        "category": None,
                        "item_name": None,
                        "record_date": None,
                    }
                )
            ]

    now = datetime(2026, 11, 10, tzinfo=UTC)
    store = SqlAlchemyMarketDataStore(cast(Session, SessionFake()))
    result = store.list_record_versions("income-statements", ["000001"], periods=["2026-09-30"])
    assert result["000001"][0]["record_key"] == "hash"
    assert "payload_json" not in statements[0].selected_columns
    compiled = statements[0].compile(dialect=mysql.dialect())
    assert ["2026-09-30"] in compiled.params.values()
    assert "json_extract" in str(compiled)


def test_missing_bar_query_only_projects_missing_dates_and_does_not_load_calendar_or_ohlc():
    statements = []

    class SessionFake:
        def scalars(self, statement):
            statements.append(statement)
            return [date(2026, 9, 25)]

    store = SqlAlchemyMarketDataStore(cast(Session, SessionFake()))
    assert store.missing_bar_days("000001", date(2026, 9, 24), date(2026, 9, 28)) == [
        date(2026, 9, 25)
    ]
    sql = str(
        statements[0].compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert len(statements[0].selected_columns) == 1
    assert "LEFT OUTER JOIN" in sql and "symbol = '000001'" in sql
    assert "2026-09-24" in sql and "2026-09-28" in sql and "IS NULL" in sql


def test_status_snapshot_latest_read_is_bounded_per_symbol_batch_and_only_decodes_latest():
    import json

    statements = []
    payload = {
        "symbol": "000001",
        "record_key": "first",
        "available_at": "2026-09-01T00:00:00+00:00",
        "status": "active",
    }

    class SessionFake:
        def scalars(self, statement):
            statements.append(statement)
            return [json.dumps(payload)]

    store = SqlAlchemyMarketDataStore(cast(Session, SessionFake()))
    assert store.latest_records("security-status", ["000001"])["000001"] == payload
    sql = str(
        statements[0].compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "row_number() OVER (PARTITION BY" in sql and "position = 1" in sql
    assert "IN ('000001')" in sql and "security-status" in sql


def test_instrument_cursor_and_lease_check_select_only_required_columns(fixed_now):
    statements = []

    class SessionFake:
        def scalars(self, statement):
            statements.append(statement)
            return ["000002"]

        def scalar(self, statement):
            statements.append(statement)
            return "job"

        def commit(self):
            pass

    session = cast(Session, SessionFake())
    assert SqlAlchemyMarketDataStore(session).instrument_candidates("000001", "daily-bars") == [
        {"symbol": "000002"}
    ]
    assert list(statements[0].selected_columns.keys()) == ["symbol"]
    assert "LIMIT" in str(statements[0].compile(dialect=mysql.dialect()))
    assert SqlAlchemyJobRepository(session).is_claim_current("job", "w", 1, fixed_now)
    assert list(statements[1].selected_columns.keys()) == ["id"]


def test_fresh_stock_batch_skips_100_in_one_claim_without_waiting_or_rescanning_all_stocks():
    container, calls, registry, job = setup_collection()
    handler = registry.get(job.job_type)
    handler(job)
    state = job.payload["collection"]
    state["unit"] = next(
        i for i, unit in enumerate(units(date(2026, 9, 28))) if unit["dataset"] == "daily-bars"
    )
    now = container.authentication.clock.now()
    container.market_data.upsert_instruments([{"symbol": f"{i:06d}"} for i in range(250)])
    for i in range(250):
        container.collection_checkpoints[f"daily-bars:{i:06d}"] = {
            "completed_at": now.isoformat(),
            "bar_day": state["bar_day"],
        }

    def unexpected():
        raise AssertionError("must not read full universe or calendar per claim")

    container.market_data.list_instruments = unexpected
    container.market_data.list_trading_days = unexpected
    result = handler(job)
    assert isinstance(result, JobContinuation) and result.resume_at == now
    assert state["last_symbol"] == "000099"
    assert len(calls) == 1
    handler(job)
    assert state["last_symbol"] == "000199"


def test_skipping_fresh_history_does_not_extend_refresh_deadline():
    container, _, registry, job = setup_collection()
    handler = registry.get(job.job_type)
    handler(job)
    handler(job)
    state = job.payload["collection"]
    key = "balance-sheets:2026-06-30"
    previous = {
        "completed_at": (container.authentication.clock.now() - timedelta(hours=1)).isoformat()
    }
    container.collection_checkpoints[key] = previous.copy()
    result = handler(job)
    assert container.collection_checkpoints[key] == previous
    assert (
        isinstance(result, JobContinuation)
        and result.resume_at == container.authentication.clock.now()
    )
    assert state["unit"] == 3


def test_request_budget_crosses_claims_releases_read_session_and_does_not_poll_db_each_second():
    container = make_test_container()
    clock = cast(FixedClock, container.authentication.clock)
    registry = JobHandlerRegistry()
    requests, checks, released = [], [], []
    original_check = container.jobs.is_claim_current

    def check(*args):
        checks.append(clock.now())
        return original_check(*args)

    container.jobs.is_claim_current = check

    class Sleeper:
        def sleep(self, seconds):
            clock.advance(timedelta(seconds=seconds))

    def handler(job):
        def send(request):
            assert released
            requests.append(clock.now())
            return httpx.Response(200)

        with httpx.Client(
            transport=httpx.MockTransport(send), event_hooks={"request": [before_data_request]}
        ) as client:
            client.get("https://fixture.invalid/data")
        return JobContinuation({}, clock.now())

    registry.register("market-data-collection", handler)
    container.jobs.enqueue(Job("a", "market-data-collection", "a", {}, clock.now()))
    worker = Worker(
        "w",
        container.jobs,
        registry,
        clock,
        Sleeper(),
        session_cleanup=lambda: released.append(clock.now()),
    )
    worker.run_once()
    worker.run_once()
    assert requests[1] - requests[0] == timedelta(seconds=5)
    assert len(checks) == 2

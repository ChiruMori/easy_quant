import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from easy_quant.application.services.acquisition import (
    AcquisitionFailed,
    AcquisitionService,
    ExponentialRetry,
)
from easy_quant.application.services.market_data_sync import MarketDataSyncService
from easy_quant.application.services.strategy_validation import extract_factor_dependencies
from easy_quant.bootstrap import ensure_dataset_catalog
from easy_quant.domain.market_data.entities import RawEnvelope, SemanticRequest
from easy_quant.domain.strategies.entities import StrategyRunStatus, StrategyVersion
from easy_quant.infrastructure.data_sources.financial_normalization import (
    normalize_financial,
    validate_financial_response,
)
from easy_quant.infrastructure.persistence.repositories.runtime import InMemoryMarketDataStore
from easy_quant.infrastructure.strategy_runtime.runner import SubprocessStrategyRunner
from easy_quant.strategy_api.context import RuntimeContext
from tests.application.test_acquisition_service import MemoryCache, Source
from tests.fakes.core import FixedClock, VirtualSleeper


def test_legacy_financial_source_upgrade_preserves_disabled_settings_and_is_idempotent():
    datasets = [{"key": "financial-indicators", "sources": [{"key": "akshare", "enabled": False}]}]
    catalog = ensure_dataset_catalog(datasets)
    sources = next(row for row in catalog if row["key"] == "financial-indicators")["sources"]
    assert {row["key"] for row in sources} == {"eastmoney", "sina"}
    assert all(row["enabled"] is False for row in sources)
    count = len(datasets)
    ensure_dataset_catalog(datasets)
    assert len(datasets) == count


def report(period="2025-12-31", **changes):
    return normalize_financial(
        "financial-indicators",
        "000001",
        {
            "REPORT_DATE": period,
            "NOTICE_DATE": "2026-03-20",
            "UPDATE_DATE": "2026-03-21",
            "ROEJQ": "8.07",
            **changes,
        },
    )


class Feed:
    now = datetime(2026, 9, 29, tzinfo=UTC)

    def __init__(self, rows):
        self.rows = rows

    def acquire_with_attempts(self, request, **kwargs):
        if request.parameters["symbol"] == "000002":
            raise AcquisitionFailed(
                "来源失败", {"attempts": [{"source_key": "eastmoney", "status": "failed"}]}
            )
        return RawEnvelope(
            request.identity,
            "eastmoney",
            json.dumps(self.rows).encode(),
            "application/json",
            self.now,
            self.now + timedelta(hours=1),
        ), []


def test_financial_sync_is_content_idempotent_and_observed_revision_is_not_backdated():
    store = InMemoryMarketDataStore({}, {}, set())
    feed = Feed([report()])
    service = MarketDataSyncService({"financial-indicators": feed}, store)

    def sync():
        return service.sync(
            "financial-indicators",
            symbols=["000001"],
            start_day=date(2025, 1, 1),
            end_day=date(2026, 9, 30),
        )

    assert sync()["record_count"] == 1
    first = store.list_records("financial-indicators")[0].copy()
    feed.now += timedelta(days=1)
    assert sync()["unchanged_count"] == 1
    assert store.list_records("financial-indicators")[0] == first
    feed.rows = [report(ROEJQ="7.99")]
    assert sync()["record_count"] == 1
    revision = store.list_records("financial-indicators")[-1]
    assert revision["available_at"] == feed.now.isoformat()
    assert revision["availability_basis"] == "observed_revision"
    assert first["available_at"] == "2026-03-21T23:59:59+08:00"


def test_missing_revision_is_only_visible_after_fetch_and_partial_success_is_retained():
    store = InMemoryMarketDataStore({}, {}, set())
    service = MarketDataSyncService(
        {"financial-indicators": Feed([report(UPDATE_DATE=None)])}, store
    )
    with pytest.raises(AcquisitionFailed) as caught:
        service.sync(
            "financial-indicators", symbols=["000001", "000002"], end_day=date(2026, 9, 30)
        )
    assert caught.value.details["record_count"] == 1
    assert store.list_records("financial-indicators")[0]["available_at"] == Feed.now.isoformat()
    failures = caught.value.details["failed_symbols"]
    assert isinstance(failures, list) and failures[0]["symbol"] == "000002"


def test_early_report_date_is_retained_but_not_visible_before_observation():
    store = InMemoryMarketDataStore({}, {}, set())
    row = report(NOTICE_DATE="2025-11-01", UPDATE_DATE="2025-11-02")
    feed = Feed([row])
    service = MarketDataSyncService({"financial-indicators": feed}, store)
    service.sync("financial-indicators", symbols=["000001"], end_day=date(2026, 9, 30))
    saved = store.list_records("financial-indicators")[0]
    assert saved["available_at"] == feed.now.isoformat()
    assert saved["availability_basis"] == "observed"
    assert saved["published_at"].startswith("2025-11-01")


def test_latest_revision_compares_instants_across_source_and_observed_timezones():
    from easy_quant.platform_library.financials import visible_versions

    original = {
        "report_period": "2025-12-31",
        "available_at": "2026-08-01T23:59:59+08:00",
        "revenue": "100",
    }
    revision = {**original, "available_at": "2026-08-01T17:00:00+00:00", "revenue": "200"}
    assert visible_versions([revision, original])[0]["revenue"] == "200"


def test_invalid_batch_never_partially_writes_a_stock():
    store = InMemoryMarketDataStore({}, {}, set())
    service = MarketDataSyncService(
        {"financial-indicators": Feed([report(), {"symbol": "wrong"}])}, store
    )
    with pytest.raises(AcquisitionFailed):
        service.sync("financial-indicators", symbols=["000001"], end_day=date(2026, 9, 30))
    assert not store.list_records("financial-indicators")


def test_invalid_financial_response_switches_source_before_caching(fixed_now):
    invalid = Source("eastmoney", payload=b'[{"roe":"NaN"}]')
    valid = Source("sina", payload=json.dumps([report()]).encode())
    cache = MemoryCache()
    acquisition = AcquisitionService(
        [invalid, valid],
        cache,
        FixedClock(fixed_now),
        VirtualSleeper(),
        ExponentialRetry(1, 0),
        shuffle=lambda _: None,
        validate=validate_financial_response,
        retry_by_round=True,
    )
    request = SemanticRequest("financial-indicators", {"symbol": "000001"}, "v1")
    envelope, attempts = acquisition.acquire_with_attempts(request)
    assert envelope.source_key == "sina" and [row.status for row in attempts] == [
        "failed",
        "succeeded",
    ]
    assert cache.value == envelope


def test_financial_library_selects_report_versions_after_cutoff_and_uses_decimal(fixed_now):
    records = [
        {**report(), "record_key": "original", "available_at": "2026-03-21T23:59:59+08:00"},
        {
            **report("2026-06-30", NOTICE_DATE="2026-08-01", UPDATE_DATE="2026-08-01"),
            "roe": "9.01",
            "record_key": "new-report",
            "available_at": "2026-08-01T23:59:59+08:00",
        },
        {
            **report(),
            "roe": "7.99",
            "record_key": "revision",
            "available_at": "2026-09-01T23:59:59+08:00",
        },
        {
            **report(),
            "roe": "999",
            "record_key": "future",
            "available_at": "2026-10-01T23:59:59+08:00",
        },
    ]
    data = {
        "decision_at": "2026-09-29T08:00:00+00:00",
        "records": {"financial-indicators": {"000001": records}},
    }
    context = RuntimeContext(data)
    early = RuntimeContext({**data, "decision_at": "2026-03-20T23:59:59+08:00"})
    assert early.library("financial.financial-indicators", symbol="000001") == ()
    rows = context.library("financial.financial-indicators", symbol="000001")
    assert [row["roe"] for row in rows] == [Decimal("7.99"), Decimal("9.01")]
    assert context.library("financial.financial-indicators", symbol="000001", period="annual")[0][
        "roe"
    ] == Decimal("7.99")
    assert context.library("fundamental.latest", symbol="000001", dataset="financial-indicators")[
        "roe"
    ] == Decimal("9.01")
    with pytest.raises(Exception, match="报告筛选"):
        context.library("financial.financial-indicators", symbol="000001", period="bad")
    source = (
        "def before_market(c,p):\n rows=c.library('financial.financial-indicators',"
        "symbol='000001',period='annual')\n print(rows[0]['roe']); return []"
    )
    assert extract_factor_dependencies(source) == {"financial-indicators"}
    run = SubprocessStrategyRunner().run(
        StrategyVersion("v", "s", 1, source, "h", fixed_now), {}, data
    )
    assert run.status is StrategyRunStatus.SUCCEEDED
    assert run.stdout.strip() == "7.99"

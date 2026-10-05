import json
from datetime import UTC, date, datetime, timedelta

import pytest

from easy_quant.application.services.market_data_sync import MarketDataSyncService
from easy_quant.domain.market_data.entities import (
    AttemptStatus,
    RawEnvelope,
    SourceAttempt,
)
from easy_quant.domain.shared.errors import StateConflictError
from easy_quant.infrastructure.persistence.repositories.runtime import InMemoryMarketDataStore


class FakeAcquisition:
    def __init__(self, payload: object, source: str = "fake") -> None:
        self.payload = payload
        self.source = source
        self.requests = []

    def acquire_with_attempts(self, request, *, force=False, source_keys=None):
        self.requests.append(request)
        now = datetime(2026, 10, 1, tzinfo=UTC)
        envelope = RawEnvelope(
            request.identity,
            self.source,
            json.dumps(self.payload, ensure_ascii=False).encode(),
            "application/json",
            now,
            now + timedelta(hours=1),
        )
        return envelope, [SourceAttempt(self.source, 1, AttemptStatus.SUCCEEDED)]


def test_sync_normalizes_securities_calendar_and_daily_bars() -> None:
    bars: dict[tuple[str, str], dict[str, object]] = {}
    instruments: dict[str, dict[str, object]] = {}
    days: set[str] = set()
    store = InMemoryMarketDataStore(bars, instruments, days)
    service = MarketDataSyncService(
        {
            "securities": FakeAcquisition([{"代码": "000001", "名称": "平安银行"}]),
            "trading-calendar": FakeAcquisition([{"trade_date": "2026-09-30"}]),
            "daily-bars": FakeAcquisition(
                [
                    {
                        "日期": "2026-09-30",
                        "开盘": 10,
                        "最高": 11,
                        "最低": 9,
                        "收盘": 10.5,
                        "成交量": 1000,
                    }
                ]
            ),
        },
        store,
    )

    service.sync("securities")
    service.sync("trading-calendar")
    result = service.sync(
        "daily-bars",
        symbols=["000001"],
        start_day=date(2026, 9, 30),
        end_day=date(2026, 9, 30),
    )

    assert instruments["000001"]["name"] == "平安银行"
    assert date(2026, 9, 30) in store.list_trading_days()
    assert bars[("000001", "2026-09-30")]["close"] == "10.5"
    assert result["record_count"] == 1


def test_sync_cannot_mix_qfq_with_existing_unadjusted_history() -> None:
    import pytest

    from easy_quant.domain.shared.errors import StateConflictError

    rows = {
        ("000001", "2026-09-29"): {
            "symbol": "000001",
            "trading_day": "2026-09-29",
            "close": "10",
            "adjustment": "none",
        }
    }
    store = InMemoryMarketDataStore(rows, {}, set())
    with pytest.raises(StateConflictError, match="复权口径冲突"):
        store.upsert_bars([{"symbol": "000001", "trading_day": "2026-09-30", "adjustment": "qfq"}])
    assert len(rows) == 1


def test_daily_bar_sync_uses_existing_unadjusted_history() -> None:
    rows = {
        ("000016", "2026-09-03"): {
            "symbol": "000016",
            "trading_day": "2026-09-03",
            "adjustment": "none",
        }
    }
    source = FakeAcquisition(
        [{"日期": "2026-09-04", "开盘": 10, "最高": 11, "最低": 9, "收盘": 10.5, "成交量": 100}]
    )
    store = InMemoryMarketDataStore(rows, {}, set())
    service = MarketDataSyncService({"daily-bars": source}, store)

    result = service.sync(
        "daily-bars", symbols=["000016"], start_day=date(2026, 9, 3), end_day=date(2026, 9, 4)
    )

    assert source.requests[0].parameters["adjustment"] == "none"
    assert rows[("000016", "2026-09-04")]["adjustment"] == "none"
    assert rows[("000016", "2026-09-03")]["adjustment"] == "none"
    assert result["new_record_count"] == 1
    assert result["message"] == ""


def test_daily_bar_sync_reports_no_new_trading_days() -> None:
    source = FakeAcquisition(
        [
            {
                "date": "2026-09-03",
                "open": 2.46,
                "high": 2.46,
                "low": 2.45,
                "close": 2.46,
                "volume": 1,
            }
        ]
    )
    rows = {
        ("000016", "2026-09-03"): {
            "symbol": "000016",
            "trading_day": "2026-09-03",
            "adjustment": "none",
        }
    }
    service = MarketDataSyncService(
        {"daily-bars": source}, InMemoryMarketDataStore(rows, {}, set())
    )
    result = service.sync(
        "daily-bars", symbols=["000016"], start_day=date(2026, 9, 3), end_day=date(2026, 9, 30)
    )
    assert result["record_count"] == 1
    assert result["new_record_count"] == 0
    assert "000016 最新 2026-09-03" in str(result["message"])


def test_daily_bar_sync_keeps_qfq_default_and_rejects_unknown_history() -> None:
    source = FakeAcquisition(
        [{"日期": "2026-09-04", "开盘": 10, "最高": 11, "最低": 9, "收盘": 10.5, "成交量": 100}]
    )
    store = InMemoryMarketDataStore({}, {}, set())
    service = MarketDataSyncService({"daily-bars": source}, store)
    service.sync(
        "daily-bars", symbols=["000001"], start_day=date(2026, 9, 4), end_day=date(2026, 9, 4)
    )
    assert source.requests[0].parameters["adjustment"] == "qfq"
    assert store.bar_adjustment("000001") == "qfq"

    store.daily_bars[("000002", "2026-09-03")] = {
        "symbol": "000002",
        "trading_day": "2026-09-03",
        "adjustment": "unknown",
    }
    with pytest.raises(StateConflictError, match="口径不明确"):
        service.sync(
            "daily-bars", symbols=["000002"], start_day=date(2026, 9, 4), end_day=date(2026, 9, 4)
        )
    assert len(source.requests) == 1


def test_daily_bar_cache_identity_includes_adjustment() -> None:
    source = FakeAcquisition([])
    store = InMemoryMarketDataStore(
        {
            ("000016", "2026-09-03"): {
                "symbol": "000016",
                "trading_day": "2026-09-03",
                "adjustment": "none",
            }
        },
        {},
        set(),
    )
    service = MarketDataSyncService({"daily-bars": source}, store)

    service.sync(
        "daily-bars", symbols=["000016"], start_day=date(2026, 9, 4), end_day=date(2026, 9, 4)
    )
    store.daily_bars[("000016", "2026-09-03")]["adjustment"] = "qfq"
    service.sync(
        "daily-bars", symbols=["000016"], start_day=date(2026, 9, 4), end_day=date(2026, 9, 4)
    )

    assert source.requests[0].parameters["adjustment"] == "none"
    assert source.requests[1].parameters["adjustment"] == "qfq"
    assert source.requests[0].identity != source.requests[1].identity


def test_mixed_historical_adjustments_are_rejected_before_acquisition() -> None:
    source = FakeAcquisition([])
    store = InMemoryMarketDataStore(
        {
            ("000001", "2026-09-02"): {
                "symbol": "000001",
                "trading_day": "2026-09-02",
                "adjustment": "none",
            },
            ("000001", "2026-09-03"): {
                "symbol": "000001",
                "trading_day": "2026-09-03",
                "adjustment": "qfq",
            },
        },
        {},
        set(),
    )
    service = MarketDataSyncService({"daily-bars": source}, store)
    with pytest.raises(StateConflictError, match="多种日线复权口径"):
        service.sync(
            "daily-bars", symbols=["000001"], start_day=date(2026, 9, 4), end_day=date(2026, 9, 4)
        )
    assert source.requests == []


def test_full_security_refresh_marks_missing_instruments_delisted() -> None:
    instruments = {
        "000001": {"symbol": "000001", "name": "旧名称", "status": "active"},
        "000002": {"symbol": "000002", "name": "退市股票", "status": "active"},
    }
    store = InMemoryMarketDataStore({}, instruments, set())
    source = FakeAcquisition([{"代码": "000001", "名称": "新名称"}])
    service = MarketDataSyncService({"securities": source}, store)

    service.sync("securities", symbols=["000001"])
    assert instruments["000002"]["status"] == "active"

    source.payload = []
    with pytest.raises(ValueError, match="清单为空"):
        service.sync("securities")
    assert instruments["000002"]["status"] == "active"

    source.payload = {"data": {"total": 2, "diff": [{"f12": "000001", "f14": "新名称"}]}}
    with pytest.raises(ValueError, match="清单不完整"):
        service.sync("securities")
    assert instruments["000002"]["status"] == "active"

    source.payload = [{"代码": "000001", "名称": "新名称"}]
    service.sync("securities")
    assert instruments["000001"]["status"] == "active"
    assert instruments["000002"] == {"symbol": "000002", "name": "退市股票", "status": "delisted"}

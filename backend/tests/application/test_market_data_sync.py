import json
from datetime import UTC, date, datetime, timedelta

import pytest

from easy_quant.application.services.acquisition import AcquisitionFailed
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
        self.source_keys = []

    def acquire_with_attempts(self, request, *, force=False, source_keys=None):
        self.requests.append(request)
        self.source_keys.append(source_keys)
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


def test_explicit_suspension_in_securities_is_not_mistaken_for_delisting():
    store = InMemoryMarketDataStore({}, {}, set())
    service = MarketDataSyncService(
        {"securities": FakeAcquisition([{"code": "600293", "status": "停牌"}])}, store
    )
    service.sync("securities")
    assert (store.get_instrument("600293") or {})["status"] == "suspended"


def test_suspension_sync_updates_only_confirmed_symbols_and_skips_daily_acquisition():
    store = InMemoryMarketDataStore({}, {}, set())
    symbols = ["600293", "601059", "601198", "688496"]
    store.upsert_instruments([{"symbol": symbol, "status": "active"} for symbol in symbols])
    store.upsert_instruments([{"symbol": "000001", "status": "suspended"}])
    feed = FakeAcquisition(
        [{"symbol": symbol, "status": "suspended", "as_of_day": "2026-09-30"} for symbol in symbols]
    )
    daily = FakeAcquisition([])
    service = MarketDataSyncService({"trading-status": feed, "daily-bars": daily}, store)
    result = service.sync("trading-status", end_day=date(2026, 9, 30))
    assert result["record_count"] == 4
    assert all((store.get_instrument(symbol) or {})["status"] == "suspended" for symbol in symbols)
    assert len(store.list_records("security-status")) == 4
    feed.payload = []
    service.sync("trading-status", end_day=date(2026, 9, 30))
    assert (store.get_instrument("600293") or {})["status"] == "suspended"
    assert (store.get_instrument("000001") or {})["status"] == "suspended"
    assert daily.requests
    daily.requests.clear()
    result = service.sync(
        "daily-bars", symbols=symbols, start_day=date(2026, 9, 1), end_day=date(2026, 9, 30)
    )
    assert not daily.requests
    assert result["skipped_suspended_symbols"] == sorted(symbols)
    assert not store.list_records("daily-bar-availability")


def test_invalid_suspension_batch_does_not_partially_update():
    store = InMemoryMarketDataStore({}, {}, set())
    store.upsert_instruments([{"symbol": "600293", "status": "active"}])
    service = MarketDataSyncService(
        {
            "trading-status": FakeAcquisition(
                [
                    {"symbol": "600293", "status": "suspended", "as_of_day": "2026-09-30"},
                    {"symbol": "601059", "status": "active"},
                ]
            )
        },
        store,
    )
    with pytest.raises(ValueError):
        service.sync("trading-status", end_day=date(2026, 9, 30))
    assert (store.get_instrument("600293") or {})["status"] == "active"


def _traded_bar(day="2026-09-30", volume="100", close="10"):
    return {"date": day, "open": "10", "high": "11", "low": "9", "close": close, "volume": volume}


def test_automatic_resumption_uses_traded_day_and_enabled_sources_and_is_idempotent():
    store = InMemoryMarketDataStore({}, {}, set())
    store.upsert_instruments(
        [
            {"symbol": "600293", "name": "三峡新材", "status": "suspended"},
            {"symbol": "000001", "status": "delisted"},
        ]
    )
    daily = FakeAcquisition([_traded_bar()], "confirmed-source")
    service = MarketDataSyncService(
        {"trading-status": FakeAcquisition([]), "daily-bars": daily}, store
    )
    result = service.sync(
        "trading-status", end_day=date(2026, 9, 30), confirmation_source_keys={"confirmed-source"}
    )
    assert result["resumed_symbols"] == ["600293"]
    assert result["unconfirmed_symbols"] == []
    assert (store.get_instrument("600293") or {})["status"] == "active"
    assert (store.get_instrument("000001") or {})["status"] == "delisted"
    assert len(daily.requests) == 1
    assert daily.requests[0].parameters == {
        "symbol": "600293",
        "start_date": "2026-09-30",
        "end_date": "2026-09-30",
        "adjustment": "none",
    }
    assert daily.source_keys == [{"confirmed-source"}]
    record = store.list_records("security-status")[0]
    assert record["previous_status"] == "suspended"
    assert record["status"] == "active"
    assert record["source"] == "confirmed-source"
    assert record["evidence"] == "traded-daily-bar"
    assert record["evidence_volume"] == "100"
    service.sync("trading-status", end_day=date(2026, 9, 30))
    assert len(daily.requests) == 1
    assert len(store.list_records("security-status")) == 1


@pytest.mark.parametrize(
    "payload",
    [
        [],
        [_traded_bar("2026-09-29")],
        [_traded_bar("2026-10-01")],
        [_traded_bar(volume="0")],
        [_traded_bar(volume="NaN")],
        [_traded_bar(close="0")],
        [_traded_bar(close="NaN")],
    ],
)
def test_absent_suspension_or_invalid_trading_evidence_does_not_resume(payload):
    store = InMemoryMarketDataStore({}, {}, set())
    store.upsert_instruments([{"symbol": "600293", "status": "suspended"}])
    daily = FakeAcquisition(payload)
    service = MarketDataSyncService(
        {"trading-status": FakeAcquisition([]), "daily-bars": daily}, store
    )
    result = service.sync("trading-status", end_day=date(2026, 9, 30))
    assert result["unconfirmed_symbols"] == ["600293"]
    assert (store.get_instrument("600293") or {})["status"] == "suspended"
    # 下一次盘后自动重试，不需要人工操作。
    daily.payload = [_traded_bar()]
    result = service.sync("trading-status", end_day=date(2026, 9, 30))
    assert result["resumed_symbols"] == ["600293"]


def test_confirmation_failure_keeps_status_and_exposes_source_attempts():
    store = InMemoryMarketDataStore({}, {}, set())
    store.upsert_instruments([{"symbol": "600293", "status": "suspended"}])

    class FailedAcquisition:
        def acquire_with_attempts(self, *_args, **_kwargs):
            raise AcquisitionFailed(
                "所有数据来源均失败",
                {
                    "attempts": [
                        {
                            "source_key": "fake",
                            "attempt": 1,
                            "status": "failed",
                            "message": "连接中断",
                        }
                    ]
                },
            )

    service = MarketDataSyncService(
        {"trading-status": FakeAcquisition([]), "daily-bars": FailedAcquisition()}, store
    )
    result = service.sync("trading-status", end_day=date(2026, 9, 30))
    assert result["unconfirmed_symbols"] == ["600293"]
    assert "下次盘后自动重试" in str(result["message"])
    attempts = result["attempts"]
    assert isinstance(attempts, list)
    assert attempts[-1]["purpose"] == "resume-confirmation"
    assert (store.get_instrument("600293") or {})["status"] == "suspended"


def test_historical_status_replay_cannot_undo_a_later_suspension():
    store = InMemoryMarketDataStore({}, {}, set())
    store.upsert_instruments([{"symbol": "600293", "status": "suspended"}])
    daily = FakeAcquisition([_traded_bar("2026-09-28")])
    service = MarketDataSyncService(
        {"trading-status": FakeAcquisition([]), "daily-bars": daily}, store
    )
    with pytest.raises(ValueError, match="不得覆盖当前状态"):
        service.sync("trading-status", end_day=date(2026, 9, 28))
    assert not daily.requests
    assert (store.get_instrument("600293") or {})["status"] == "suspended"


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

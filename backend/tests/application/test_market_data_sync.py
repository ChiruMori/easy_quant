import json
from datetime import UTC, date, datetime, timedelta

from easy_quant.application.services.market_data_sync import MarketDataSyncService
from easy_quant.domain.market_data.entities import (
    AttemptStatus,
    RawEnvelope,
    SourceAttempt,
)
from easy_quant.infrastructure.persistence.repositories.runtime import InMemoryMarketDataStore


class FakeAcquisition:
    def __init__(self, payload: object, source: str = "fake") -> None:
        self.payload = payload
        self.source = source

    def acquire_with_attempts(self, request, *, force=False, source_keys=None):
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

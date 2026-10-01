from datetime import UTC, date, datetime

from easy_quant.domain.market_data.calendar import FreshnessStatus, TradingCalendar


def test_updated_always_uses_previous_trading_day_even_after_close() -> None:
    calendar = TradingCalendar({date(2026, 9, 30), date(2026, 10, 1)})
    result = calendar.freshness(
        first_day=date(2020, 1, 1),
        last_day=date(2026, 9, 30),
        now=datetime(2026, 10, 1, 8, 0, tzinfo=UTC),  # 上海时间 16:00
    )
    assert result.status is FreshnessStatus.UPDATED
    assert result.previous_trading_day == date(2026, 9, 30)
    assert result.recommended_end_day == date(2026, 10, 1)


def test_stale_history_recommends_previous_trading_day_before_close() -> None:
    calendar = TradingCalendar({date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 1)})
    result = calendar.freshness(
        first_day=date(2020, 1, 1),
        last_day=date(2026, 9, 29),
        now=datetime(2026, 10, 1, 5, 0, tzinfo=UTC),  # 上海时间 13:00
    )
    assert result.status is FreshnessStatus.STALE
    assert result.recommended_end_day == date(2026, 9, 30)

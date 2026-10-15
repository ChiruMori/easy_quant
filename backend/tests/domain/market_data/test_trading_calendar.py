from datetime import UTC, date, datetime

from easy_quant.domain.market_data.calendar import FreshnessStatus, TradingCalendar


def test_data_before_nightly_publish_uses_previous_trading_day() -> None:
    calendar = TradingCalendar({date(2026, 9, 30), date(2026, 10, 1)})
    result = calendar.freshness(
        first_day=date(2020, 1, 1),
        last_day=date(2026, 9, 30),
        now=datetime(2026, 10, 1, 8, 0, tzinfo=UTC),  # 上海时间 16:00
    )
    assert result.status is FreshnessStatus.UPDATED
    assert result.previous_trading_day == date(2026, 9, 30)
    assert result.recommended_end_day == date(2026, 9, 30)


def test_stale_history_recommends_previous_trading_day_before_close() -> None:
    calendar = TradingCalendar({date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 1)})
    result = calendar.freshness(
        first_day=date(2020, 1, 1),
        last_day=date(2026, 9, 29),
        now=datetime(2026, 10, 1, 5, 0, tzinfo=UTC),  # 上海时间 13:00
    )
    assert result.status is FreshnessStatus.STALE
    assert result.recommended_end_day == date(2026, 9, 30)


def test_expired_calendar_does_not_freeze_freshness_at_last_import() -> None:
    calendar = TradingCalendar({date(2015, 1, 5), date(2026, 10, 8)})
    for hour, expected in ((8, date(2026, 10, 14)), (15, date(2026, 10, 15))):
        result = calendar.freshness(
            first_day=date(2015, 1, 5),
            last_day=date(2026, 10, 8),
            now=datetime(2026, 10, 15, hour, tzinfo=UTC),
        )
        assert result.status is FreshnessStatus.STALE
        assert result.recommended_end_day == expected
        assert calendar.is_estimated(expected)


def test_known_holiday_and_weekend_do_not_require_unpublished_bars() -> None:
    calendar = TradingCalendar({date(2026, 9, 30), date(2026, 10, 8), date(2026, 10, 9)})
    for day, latest in (
        (date(2026, 10, 5), date(2026, 9, 30)),
        (date(2026, 10, 11), date(2026, 10, 9)),
    ):
        result = calendar.freshness(
            first_day=date(2015, 1, 5),
            last_day=latest,
            now=datetime(day.year, day.month, day.day, 15, tzinfo=UTC),
        )
        assert result.status is FreshnessStatus.UPDATED
        assert result.recommended_end_day == latest

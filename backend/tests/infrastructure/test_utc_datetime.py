from datetime import UTC, datetime, timedelta, timezone

from easy_quant.infrastructure.persistence.base import UtcDateTime


def test_database_datetime_is_stored_as_utc_and_restored_with_timezone() -> None:
    column = UtcDateTime()
    beijing = timezone(timedelta(hours=8))
    instant = datetime(2026, 10, 3, 19, 23, 32, tzinfo=beijing)

    stored = column.process_bind_param(instant, None)
    assert stored == datetime(2026, 10, 3, 11, 23, 32)
    assert column.process_result_value(stored, None) == datetime(
        2026, 10, 3, 11, 23, 32, tzinfo=UTC
    )

from datetime import UTC, datetime

from easy_quant.application.services.scheduled_tasks import ScheduledTaskService, next_run
from easy_quant.domain.scheduling.entities import ScheduledTask, ScheduleKind


def test_interval_cron_timezone_enable_and_history() -> None:
    now = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    interval = ScheduledTask("i", "data", ScheduleKind.INTERVAL, "60", "UTC", {}, now)
    assert next_run(interval, now).minute == 1
    cron = ScheduledTask("c", "data", ScheduleKind.CRON, "0 9 * * *", "Asia/Shanghai", {}, now)
    assert next_run(cron, now).hour == 1
    service = ScheduledTaskService()
    service.save(interval)
    service.set_enabled("i", False, now)
    service.set_enabled("i", True, now)
    assert interval.enabled and len(service.history) == 2


def test_weekday_cron_skips_weekend() -> None:
    task = ScheduledTask(
        "weekday",
        "market-data-acquisition",
        ScheduleKind.CRON,
        "0 18 * * 1-5",
        "Asia/Shanghai",
        {},
        datetime(2026, 10, 2, 10, tzinfo=UTC),
    )

    result = next_run(task, datetime(2026, 10, 2, 10, tzinfo=UTC))

    assert result == datetime(2026, 10, 5, 10, tzinfo=UTC)

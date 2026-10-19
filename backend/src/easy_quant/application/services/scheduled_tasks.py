from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from easy_quant.domain.market_data.indices import INDEX_CATALOG
from easy_quant.domain.scheduling.entities import ScheduledTask, ScheduleKind
from easy_quant.domain.shared.errors import ValidationError
from easy_quant.domain.shared.value_objects import ensure_utc


def validate_index_configuration(configuration: dict) -> None:
    symbols = configuration.get("symbols", list(INDEX_CATALOG))
    if (
        not isinstance(symbols, list)
        or not symbols
        or any(not isinstance(symbol, str) or symbol not in INDEX_CATALOG for symbol in symbols)
        or len(set(symbols)) != len(symbols)
    ):
        raise ValidationError("请选择不重复的主要指数代码")
    try:
        start = (
            date.fromisoformat(configuration["start_day"]) if "start_day" in configuration else None
        )
        end = date.fromisoformat(configuration["end_day"]) if "end_day" in configuration else None
    except (ValueError, TypeError) as error:
        raise ValidationError("指数日期必须为 YYYY-MM-DD") from error
    if start and end and start > end:
        raise ValidationError("开始日期不得晚于结束日期")


def next_run(task: ScheduledTask, after: datetime) -> datetime:
    after = ensure_utc(after)
    if task.schedule_kind is ScheduleKind.INTERVAL:
        try:
            seconds = int(task.schedule_expression)
        except ValueError as error:
            raise ValidationError("固定间隔必须为秒数") from error
        if seconds <= 0:
            raise ValidationError("固定间隔必须大于零")
        return after + timedelta(seconds=seconds)
    parts = task.schedule_expression.split()
    if len(parts) != 5:
        raise ValidationError("cron 表达式必须包含五段")
    try:
        local = after.astimezone(ZoneInfo(task.timezone))
        minutes = _cron_values(parts[0], 0, 59)
        hours = _cron_values(parts[1], 0, 23)
        month_days = _cron_values(parts[2], 1, 31)
        months = _cron_values(parts[3], 1, 12)
        weekdays = _cron_values(parts[4], 0, 7)
    except (ValueError, KeyError) as error:
        raise ValidationError("cron 或时区无效") from error
    candidate = local.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(60 * 24 * 366 * 2):
        cron_weekday = (candidate.weekday() + 1) % 7
        if (
            candidate.minute in minutes
            and candidate.hour in hours
            and candidate.day in month_days
            and candidate.month in months
            and (cron_weekday in weekdays or (cron_weekday == 0 and 7 in weekdays))
        ):
            return candidate.astimezone(ZoneInfo("UTC"))
        candidate += timedelta(minutes=1)
    raise ValidationError("cron 表达式在两年内没有可运行时间")


def _cron_values(expression: str, minimum: int, maximum: int) -> set[int]:
    if expression == "*":
        return set(range(minimum, maximum + 1))
    values: set[int] = set()
    for part in expression.split(","):
        if "-" in part:
            start, end = (int(value) for value in part.split("-", 1))
            if start > end:
                raise ValueError
            values.update(range(start, end + 1))
        else:
            values.add(int(part))
    if not values or min(values) < minimum or max(values) > maximum:
        raise ValueError
    return values


class ScheduledTaskService:
    def __init__(self) -> None:
        self.tasks: dict[str, ScheduledTask] = {}
        self.history: list[dict[str, object]] = []

    def save(self, task: ScheduledTask) -> ScheduledTask:
        self.tasks[task.id] = task
        return task

    def set_enabled(self, task_id: str, enabled: bool, now: datetime) -> ScheduledTask:
        task = self.tasks[task_id]
        task.enabled = enabled
        if enabled:
            task.next_run_at = next_run(task, now)
        self.history.append({"task_id": task_id, "enabled": enabled, "at": ensure_utc(now)})
        return task

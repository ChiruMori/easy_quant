from datetime import datetime, time


def ensure_data_schedule(schedules, now: datetime, publish_time: str) -> None:
    """仅补齐缺失计划，已有管理员时刻和停用选择不覆盖。"""
    if any(row.get("task_type") == "market-data-nightly" for row in schedules.values()):
        return
    identifier = "schedule-market-data-nightly"
    if identifier in schedules:
        return
    at = time.fromisoformat(publish_time)
    schedules[identifier] = {
        "id": identifier,
        "task_type": "market-data-nightly",
        "schedule_kind": "cron",
        "schedule_expression": f"{at.minute} {at.hour} * * 1-5",
        "timezone": "Asia/Shanghai",
        "configuration": {},
        "enabled": True,
        "next_run_at": now.isoformat(),
    }

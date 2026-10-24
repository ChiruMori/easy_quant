from easy_quant.application.services.scheduled_tasks import next_run
from easy_quant.domain.scheduling.entities import ScheduledTask, ScheduleKind


def is_live_schedule(row):
    return row.get("task_type") in {"live-analysis", "live.analyze"}


def sync_live_schedules(container, instance_id: str, *, create=False):
    """实盘计划由实例状态驱动，不接受系统任务管理页独立维护。"""
    instance = container.state.live_instances.get(instance_id)
    schedules = container.state.schedules
    linked = [
        (key, dict(row))
        for key, row in schedules.items()
        if is_live_schedule(row) and row.get("configuration", {}).get("instance_id") == instance_id
    ]
    if instance is None or instance.get("status") == "terminated":
        for key, _ in linked:
            del schedules[key]
        return []
    hour, minute = container.settings.intraday_run_time.split(":")[:2]
    phases = {"before_market": "0 9 * * 1-5", "on_market": f"{int(minute)} {int(hour)} * * 1-5"}
    if instance.get("after_market_enabled", False):
        phases["after_market"] = "30 15 * * 1-5"
    seen = set()
    now = container.authentication.clock.now()
    for key, row in linked:
        phase = row.get("configuration", {}).get("phase")
        if phase not in phases or phase in seen:
            del schedules[key]
            continue
        seen.add(phase)
        enabled = instance.get("status") == "active"
        if row.get("enabled", True) != enabled:
            row["enabled"] = enabled
            if enabled:
                row["next_run_at"] = next_run(
                    ScheduledTask(
                        key,
                        "live-analysis",
                        ScheduleKind.CRON,
                        phases[phase],
                        "Asia/Shanghai",
                        row["configuration"],
                        now,
                    ),
                    now,
                ).isoformat()
            schedules[key] = row
    if create:
        for phase, expression in phases.items():
            if phase in seen:
                continue
            key = f"live-schedule:{instance_id}:{phase}"
            configuration = {"instance_id": instance_id, "phase": phase}
            schedules[key] = {
                "id": key,
                "task_type": "live-analysis",
                "schedule_kind": "cron",
                "schedule_expression": expression,
                "timezone": "Asia/Shanghai",
                "enabled": instance.get("status") == "active",
                "configuration": configuration,
                "next_run_at": next_run(
                    ScheduledTask(
                        key,
                        "live-analysis",
                        ScheduleKind.CRON,
                        expression,
                        "Asia/Shanghai",
                        configuration,
                        now,
                    ),
                    now,
                ).isoformat(),
            }
    return [
        dict(row)
        for row in schedules.values()
        if is_live_schedule(row) and row.get("configuration", {}).get("instance_id") == instance_id
    ]


def reconcile_live_schedules(container):
    identifiers = {
        str(row.get("configuration", {}).get("instance_id", ""))
        for row in container.state.schedules.values()
        if is_live_schedule(row)
    }
    for identifier in identifiers:
        sync_live_schedules(container, identifier)

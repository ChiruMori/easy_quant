import hashlib

from flask import Blueprint, g, request

from easy_quant.api.dependencies import get_container
from easy_quant.api.middleware.auth import require_admin
from easy_quant.api.responses import success
from easy_quant.application.services.audit_runtime import record_audit
from easy_quant.application.services.scheduled_tasks import next_run
from easy_quant.domain.market_data.calendar import TradingCalendar
from easy_quant.domain.scheduling.entities import Job, ScheduledTask, ScheduleKind
from easy_quant.domain.shared.errors import StateConflictError, ValidationError
from easy_quant.infrastructure.core import UuidGenerator

blueprint = Blueprint("admin_scheduling", __name__, url_prefix="/api/v1/admin")


def validate_schedule(payload):
    if payload.get("task_type", "market-data-acquisition") not in {
        "market-data-acquisition",
        "market-data-nightly",
        "tdx-daily-update",
        "live-analysis",
    }:
        raise ValidationError("不支持的任务类型")
    if "enabled" in payload and not isinstance(payload["enabled"], bool):
        raise ValidationError("启停状态必须为布尔值")
    if "configuration" in payload and not isinstance(payload["configuration"], dict):
        raise ValidationError("任务配置必须为 JSON 对象")
    try:
        ScheduleKind(str(payload.get("schedule_kind", "cron")))
    except ValueError as error:
        raise ValidationError("计划方式无效") from error


@blueprint.get("/schedules")
@require_admin
def schedules():
    return success(list(get_container().state.schedules.values()))


@blueprint.post("/schedules")
@require_admin
def create_schedule():
    payload = request.get_json() or {}
    validate_schedule(payload)
    schedules = get_container().state.schedules
    identifier = f"schedule-{UuidGenerator().new()}"
    now = get_container().authentication.clock.now()
    schedule_kind = ScheduleKind(str(payload.get("schedule_kind", "cron")))
    expression = str(payload.get("schedule_expression", "0 18 * * 1-5"))
    timezone = str(payload.get("timezone", "Asia/Shanghai"))
    calculated_next_run = next_run(
        ScheduledTask(
            identifier,
            str(payload.get("task_type", "market-data-acquisition")),
            schedule_kind,
            expression,
            timezone,
            dict(payload.get("configuration", {})),
            now,
        ),
        now,
    )
    item = {
        "task_type": str(payload.get("task_type", "market-data-acquisition")),
        "schedule_kind": schedule_kind.value,
        "schedule_expression": expression,
        "timezone": timezone,
        "enabled": bool(payload.get("enabled", True)),
        "id": identifier,
        "configuration": payload.get(
            "configuration",
            {"mode": "daily-update"}
            if payload.get("task_type") == "market-data-acquisition"
            else {},
        ),
        "next_run_at": calculated_next_run.isoformat(),
    }
    schedules[identifier] = item
    record_audit(
        get_container(),
        actor_user_id=g.current_user.id,
        action="create",
        resource_type="schedule",
        resource_id=identifier,
        after={"task_type": str(item.get("task_type")), "enabled": bool(item.get("enabled"))},
    )
    return success(item, status=201)


@blueprint.patch("/schedules/<schedule_id>")
@require_admin
def update_schedule(schedule_id: str):
    schedules = get_container().state.schedules
    existing = schedules.get(schedule_id)
    if existing is None:
        return success(None, status=404)
    item = dict(existing)
    before = dict(item)
    payload = request.get_json() or {}
    allowed = {
        "enabled",
        "task_type",
        "schedule_kind",
        "schedule_expression",
        "timezone",
        "configuration",
    }
    if set(payload) - allowed:
        raise ValidationError("包含不允许更新的计划字段")
    if item.get("enabled", True) and set(payload) - {"enabled"}:
        raise StateConflictError("请先停用任务，再修改计划")
    item.update(payload)
    validate_schedule(item)
    now = get_container().authentication.clock.now()
    try:
        task = ScheduledTask(
            schedule_id,
            str(item["task_type"]),
            ScheduleKind(str(item["schedule_kind"])),
            str(item["schedule_expression"]),
            str(item["timezone"]),
            dict(item.get("configuration", {})),
            now,
        )
    except (ValueError, TypeError) as error:
        raise ValidationError("定时任务配置无效") from error
    item["next_run_at"] = next_run(task, now).isoformat()
    schedules[schedule_id] = item
    record_audit(
        get_container(),
        actor_user_id=g.current_user.id,
        action="update",
        resource_type="schedule",
        resource_id=schedule_id,
        before={"enabled": bool(before.get("enabled"))},
        after={"enabled": bool(item.get("enabled"))},
    )
    return success(item)


@blueprint.post("/schedules/<schedule_id>/run")
@require_admin
def run_schedule(schedule_id: str):
    container = get_container()
    item = container.state.schedules.get(schedule_id)
    if item is None:
        return success(None, status=404)
    key = request.headers.get("Idempotency-Key", "")
    if not key or len(key) > 128:
        raise ValidationError("手动执行必须提供有效 Idempotency-Key")
    now = container.authentication.clock.now()
    task_type = str(item["task_type"])
    if task_type not in {
        "market-data-acquisition",
        "market-data-nightly",
        "tdx-daily-update",
        "live-analysis",
    }:
        raise ValidationError("不支持的任务类型")
    payload = dict(item.get("configuration", {}))
    if task_type == "market-data-acquisition" and payload.get("mode") == "daily-update":
        calendar = TradingCalendar(container.market_data.list_trading_days() or None)
        day = calendar.freshness(
            first_day=None, last_day=None, now=now
        ).recommended_end_day.isoformat()
        payload.update(
            {
                "start_day": day,
                "end_day": day,
                "dataset_key": "daily-bars",
                "symbols": [str(row["symbol"]) for row in container.market_data.list_instruments()],
            }
        )
    if task_type == "live-analysis" and not payload.get("instance_id"):
        raise ValidationError("实盘分析任务缺少实例配置")
    job_id = f"job-{UuidGenerator().new()}"
    job = container.jobs.enqueue(
        Job(
            job_id,
            task_type,
            f"manual:{g.current_user.id}:{schedule_id}:{hashlib.sha256(key.encode()).hexdigest()}",
            payload,
            now,
        )
    )
    if job.job_type != task_type or job.payload != payload:
        raise StateConflictError("幂等键已用于其他配置，请使用新的执行请求")
    if job.id != job_id:
        return success({"id": job.id, "status": job.status.value}, status=202)
    record_audit(
        container,
        actor_user_id=g.current_user.id,
        action="manual-run",
        resource_type="schedule",
        resource_id=schedule_id,
        after={"job_id": job.id, "task_type": task_type},
    )
    return success({"id": job.id, "status": job.status.value}, status=202)


@blueprint.get("/jobs")
@require_admin
def jobs():
    repository = get_container().jobs
    if repository is None:
        return success(list(get_container().state.jobs))
    now = get_container().authentication.clock.now()
    return success(
        [
            {
                "id": item.id,
                "job_type": item.job_type,
                "status": item.status.value,
                "available_at": item.available_at.isoformat(),
                "lease_until": item.lease_until.isoformat() if item.lease_until else None,
                "lease_expired": bool(
                    item.status.value == "running" and item.lease_until and item.lease_until <= now
                ),
                "attempt_count": item.attempt_count,
                "result_summary": item.result_summary,
                "error_summary": item.error_summary,
            }
            for item in repository.list_all()
        ]
    )

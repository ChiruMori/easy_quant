from datetime import UTC, datetime

from flask import Blueprint, g, request

from easy_quant.api.dependencies import get_container
from easy_quant.api.middleware.auth import require_admin
from easy_quant.api.responses import success
from easy_quant.application.services.audit_runtime import record_audit
from easy_quant.application.services.scheduled_tasks import next_run
from easy_quant.domain.scheduling.entities import ScheduledTask, ScheduleKind

blueprint = Blueprint("admin_scheduling", __name__, url_prefix="/api/v1/admin")


@blueprint.get("/schedules")
@require_admin
def schedules():
    return success(list(get_container().state.schedules.values()))


@blueprint.post("/schedules")
@require_admin
def create_schedule():
    payload = request.get_json() or {}
    schedules = get_container().state.schedules
    identifier = f"schedule-{len(schedules) + 1}"
    now = datetime.now(UTC)
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
        "id": identifier,
        **payload,
        "configuration": payload.get(
            "configuration",
            {"mode": "daily-update"}
            if payload.get("task_type") == "market-data-acquisition"
            else {},
        ),
        "next_run_at": payload.get("next_run_at") or calculated_next_run.isoformat(),
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
    item = schedules[schedule_id]
    before = dict(item)
    item.update(request.get_json() or {})
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

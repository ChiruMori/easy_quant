from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from flask import Blueprint, g, request

from easy_quant.api.dependencies import get_container
from easy_quant.api.middleware.auth import require_user
from easy_quant.api.responses import success
from easy_quant.application.services.audit_runtime import record_audit
from easy_quant.application.services.live_runtime import analyze_live_instance
from easy_quant.infrastructure.core import UuidGenerator

blueprint = Blueprint("live_tracking", __name__, url_prefix="/api/v1/live-instances")


@blueprint.post("")
@require_user
def start_live():
    payload = request.get_json() or {}
    instances = get_container().state.live_instances
    backtest = get_container().backtests.get(str(payload.get("backtest_id", "")))
    if (
        backtest is None
        or backtest.get("owner_id") != g.current_user.id
        or backtest.get("status") != "succeeded"
    ):
        return success(None, status=404)
    strategy_version_id = str(payload.get("strategy_version_id") or backtest["strategy_version_id"])
    if strategy_version_id != backtest["strategy_version_id"]:
        return success(None, status=409)
    identifier = f"live-{UuidGenerator().new()}"
    now = get_container().authentication.clock.now()
    item = {
        "id": identifier,
        "owner_id": g.current_user.id,
        "backtest_id": payload.get("backtest_id"),
        "strategy_version_id": strategy_version_id,
        "status": "active",
        "next_decision_at": (now + timedelta(days=1)).isoformat(),
        "parameters": payload.get("parameters", {}),
        "initial_cash": str(payload.get("initial_cash", backtest["config"]["initial_cash"])),
        "positions": payload.get("positions", {}),
    }
    instances[identifier] = item
    local_now = now.astimezone(ZoneInfo("Asia/Shanghai"))
    schedules = get_container().state.schedules
    schedule_specs = (
        ("before_market", "cron", "0 9 * * 1-5", time(9, 0)),
        (
            "on_market",
            "interval",
            str(get_container().settings.intraday_poll_seconds),
            None,
        ),
        ("after_market", "cron", "30 15 * * 1-5", time(15, 30)),
    )
    for phase, kind, expression, local_time in schedule_specs:
        schedule_id = f"schedule-{UuidGenerator().new()}"
        if local_time is None:
            next_run = now + timedelta(seconds=get_container().settings.intraday_poll_seconds)
        else:
            candidate = datetime.combine(local_now.date(), local_time, local_now.tzinfo)
            if candidate <= local_now:
                candidate += timedelta(days=1)
            next_run = candidate.astimezone(UTC)
        schedules[schedule_id] = {
            "id": schedule_id,
            "task_type": "live-analysis",
            "schedule_kind": kind,
            "schedule_expression": expression,
            "timezone": "Asia/Shanghai",
            "configuration": {"instance_id": identifier, "phase": phase},
            "next_run_at": next_run.isoformat(),
            "enabled": True,
        }
    record_audit(
        get_container(),
        actor_user_id=g.current_user.id,
        action="start",
        resource_type="live_instance",
        resource_id=identifier,
        after={"status": "active", "strategy_version_id": strategy_version_id},
    )
    return success(item, status=201)


@blueprint.get("")
@require_user
def list_live():
    return success(
        [
            item
            for item in get_container().state.live_instances.values()
            if item["owner_id"] == g.current_user.id
        ]
    )


@blueprint.get("/<instance_id>")
@require_user
def live_detail(instance_id: str):
    item = get_container().state.live_instances.get(instance_id)
    if item is None or item["owner_id"] != g.current_user.id:
        return success(None, status=404)
    return success(
        {**item, "recommendations": get_container().state.recommendations.get(instance_id, [])}
    )


@blueprint.post("/<instance_id>/pause")
@require_user
def pause_live(instance_id: str):
    instances = get_container().state.live_instances
    item = instances.get(instance_id)
    if item is None or item["owner_id"] != g.current_user.id:
        return success(None, status=404)
    previous_status = str(item["status"])
    item["status"] = "paused"
    instances[instance_id] = item
    record_audit(
        get_container(),
        actor_user_id=g.current_user.id,
        action="pause",
        resource_type="live_instance",
        resource_id=instance_id,
        before={"status": previous_status},
        after={"status": "paused"},
    )
    return success(item)


@blueprint.post("/<instance_id>/terminate")
@require_user
def terminate_live(instance_id: str):
    instances = get_container().state.live_instances
    item = instances.get(instance_id)
    if item is None or item["owner_id"] != g.current_user.id:
        return success(None, status=404)
    previous_status = str(item["status"])
    item["status"] = "terminated"
    instances[instance_id] = item
    for schedule_id, schedule in list(get_container().state.schedules.items()):
        if schedule.get("configuration", {}).get("instance_id") == instance_id:
            schedule["enabled"] = False
            get_container().state.schedules[schedule_id] = schedule
    record_audit(
        get_container(),
        actor_user_id=g.current_user.id,
        action="terminate",
        resource_type="live_instance",
        resource_id=instance_id,
        before={"status": previous_status},
        after={"status": "terminated"},
    )
    return success(item)


@blueprint.post("/<instance_id>/analyze/<phase>")
@require_user
def analyze_live(instance_id: str, phase: str):
    instance = get_container().state.live_instances.get(instance_id)
    if instance is None or instance["owner_id"] != g.current_user.id:
        return success(None, status=404)
    payload = request.get_json() or {}
    decision_at = (
        datetime.fromisoformat(str(payload["decision_at"]))
        if payload.get("decision_at")
        else get_container().authentication.clock.now()
    )
    return success(
        analyze_live_instance(
            get_container(),
            instance_id,
            phase,
            decision_at,
            {str(key): value for key, value in payload.get("current_prices", {}).items()},
        )
    )

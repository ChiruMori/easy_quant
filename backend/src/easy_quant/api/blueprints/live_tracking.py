from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from flask import Blueprint, g, request

from easy_quant.api.dependencies import get_container
from easy_quant.api.middleware.auth import require_user
from easy_quant.api.resource_lifecycle import delete_resource, inspect_resource, resource_mutation
from easy_quant.api.responses import success
from easy_quant.api.schemas.live_tracking import ManualOperationRequest, StartLiveRequest
from easy_quant.api.strategy_context import strategy_context
from easy_quant.application.services.audit_runtime import record_audit
from easy_quant.application.services.live_reporting import (
    operation_page,
    portfolio_summary,
    reporting_snapshot,
)
from easy_quant.application.services.live_runtime import analyze_live_instance
from easy_quant.application.services.manual_operations import ManualCommand, ManualOperationService
from easy_quant.application.services.recommendation_actions import audit_row
from easy_quant.domain.market_data.indices import is_index
from easy_quant.domain.shared.errors import NotFoundError, ValidationError
from easy_quant.infrastructure.core import UuidGenerator

blueprint = Blueprint("live_tracking", __name__, url_prefix="/api/v1/live-instances")


@blueprint.get("/<instance_id>/deletion-preview")
@require_user
def deletion_preview(instance_id: str):
    return inspect_resource("live", instance_id)


@blueprint.delete("/<instance_id>")
@require_user
def delete_live(instance_id: str):
    return delete_resource("live", instance_id)


@blueprint.post("")
@require_user
@resource_mutation
def start_live():
    payload = StartLiveRequest.model_validate(request.get_json() or {}).model_dump(mode="json")
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
    version = get_container().state.strategies.get_version(strategy_version_id)
    definition = (
        get_container().state.strategies.get_definition(version.strategy_id) if version else None
    )
    if definition is None or definition.owner_id != g.current_user.id:
        return success(None, status=404)
    if (
        backtest.get("allow_mock")
        or backtest.get("mock_usage")
        or backtest.get("config", {}).get("allow_mock")
    ):
        raise ValidationError("含 Mock 的结果不能启动实盘")
    selected = set(payload["subscription_ids"])
    owned = {
        str(row["id"])
        for row in get_container().state.subscriptions
        if row["owner_id"] == g.current_user.id and row.get("enabled", True)
    }
    if not selected <= owned:
        raise ValidationError("请选择本人启用的通知渠道")
    if any(
        not Decimal(value).is_finite() or Decimal(value) < 0 or is_index(symbol)
        for symbol, value in payload["positions"].items()
    ):
        raise ValidationError("初始持仓必须为非负有限数量，且不能持有指数")
    identifier = f"live-{UuidGenerator().new()}"
    now = get_container().authentication.clock.now()
    item = {
        "id": identifier,
        "started_at": now.isoformat(),
        "name": payload["name"].strip(),
        "subscription_ids": sorted(selected),
        "owner_id": g.current_user.id,
        "backtest_id": payload.get("backtest_id"),
        "strategy_version_id": strategy_version_id,
        "status": "active",
        "next_decision_at": (now + timedelta(days=1)).isoformat(),
        "parameters": payload["parameters"],
        "initial_cash": payload["initial_cash"],
        "positions": dict(payload["positions"]),
        "initial_positions": dict(payload["positions"]),
        "after_market_enabled": bool(payload.get("after_market_enabled", False)),
    }
    get_container().resource_lifecycle.add_live_instance(item)
    local_now = now.astimezone(ZoneInfo("Asia/Shanghai"))
    schedules = get_container().state.schedules
    intraday_time = time.fromisoformat(get_container().settings.intraday_run_time)
    schedule_specs = [
        ("before_market", "cron", "0 9 * * 1-5", time(9, 0)),
        (
            "on_market",
            "cron",
            f"{intraday_time.minute} {intraday_time.hour} * * 1-5",
            intraday_time,
        ),
    ]
    if item["after_market_enabled"]:
        schedule_specs.append(("after_market", "cron", "30 15 * * 1-5", time(15, 30)))
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
        before={"strategy_state": version.state.value},
        after={
            "status": "active",
            "strategy_version_id": strategy_version_id,
            "strategy_state": "live",
        },
    )
    return success(item, status=201)


@blueprint.get("")
@require_user
def list_live():
    return success(
        [
            _present(item)
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
    with get_container().live_tracking.transaction() as state:
        item = state.instances.get(instance_id)
        if item is None or item["owner_id"] != g.current_user.id:
            raise NotFoundError("live_instance")
        operations = operation_page(state, instance_id, 1, 20)
        snapshot = reporting_snapshot(state, instance_id)
        recommendation_ids = {row["id"] for row in state.recommendations.get(instance_id, [])}
        deliveries = [
            {
                key: row.get(key)
                for key in (
                    "id",
                    "event_id",
                    "channel",
                    "status",
                    "attempts",
                    "created_at",
                    "last_attempt_at",
                    "delivered_at",
                    "updated_at",
                    "error",
                    "error_code",
                )
            }
            for row in state.deliveries
            if row.get("owner_id") == g.current_user.id
            and (
                row.get("live_instance_id") == instance_id
                or row.get("event_id") in recommendation_ids
                or str(row.get("event_id", "")).startswith(f"{instance_id}:")
            )
        ]
        deliveries.sort(
            key=lambda row: (str(row.get("created_at") or ""), str(row["id"])), reverse=True
        )
    portfolio = portfolio_summary(
        snapshot,
        instance_id,
        get_container().market_data,
        get_container().authentication.clock.now(),
    )
    return success(
        {
            **_present(item),
            "recommendations": [
                row
                for row in operations["items"]
                if row["operation_type"] in {"buy_signal", "sell_signal"}
            ],
            "operations": operations,
            "notification_deliveries": deliveries[:20],
            "portfolio": portfolio,
        }
    )


@blueprint.get("/<instance_id>/operations")
@require_user
def live_operations(instance_id: str):
    try:
        page = int(request.args.get("page", "1"))
        page_size = int(request.args.get("page_size", "20"))
    except ValueError as error:
        raise ValidationError("分页参数必须为整数") from error
    if page < 1 or not 1 <= page_size <= 100:
        raise ValidationError("页码必须为正数，每页 1–100 条")
    status = request.args.get("status", "")
    operation_type = request.args.get("operation_type", "")
    if status not in {"", "pending", "rejected", "executed"} or operation_type not in {
        "",
        "buy_signal",
        "sell_signal",
        "manual_buy",
        "manual_sell",
    }:
        raise ValidationError("未知操作状态或类型")
    with get_container().live_tracking.transaction() as state:
        item = state.instances.get(instance_id)
        if item is None or item["owner_id"] != g.current_user.id:
            raise NotFoundError("live_instance")
        return success(
            operation_page(
                state,
                instance_id,
                page,
                page_size,
                request.args.get("search", ""),
                status,
                operation_type,
            )
        )


@blueprint.post("/<instance_id>/manual-operations/<mode>")
@require_user
@resource_mutation
def manual_operation(instance_id: str, mode: str):
    if mode not in {"preview", "record"}:
        raise NotFoundError("manual_operation")
    payload = ManualOperationRequest.model_validate(request.get_json() or {})
    container = get_container()
    return success(
        ManualOperationService(
            container.live_tracking, container.authentication.clock, UuidGenerator()
        ).apply(
            instance_id,
            g.current_user.id,
            ManualCommand(**payload.model_dump()),
            preview=mode == "preview",
        )
    )


@blueprint.post("/<instance_id>/pause")
@require_user
@resource_mutation
def pause_live(instance_id: str):
    return success(_set_status(instance_id, "paused", "pause"))


def _set_status(instance_id: str, status: str, action: str):
    container = get_container()
    with container.live_tracking.transaction() as state:
        item = state.instances.get(instance_id)
        if item is None or item["owner_id"] != g.current_user.id:
            raise NotFoundError("live_instance")
        previous_status = str(item["status"])
        item = {**item, "status": status}
        state.instances[instance_id] = item
        state.audit.append(
            audit_row(
                UuidGenerator(),
                container.authentication.clock.now(),
                g.current_user.id,
                action,
                "live_instance",
                instance_id,
                {"status": previous_status},
                {"status": status},
            )
        )
        return item


@blueprint.post("/<instance_id>/terminate")
@require_user
@resource_mutation
def terminate_live(instance_id: str):
    item = _set_status(instance_id, "terminated", "terminate")
    for schedule_id, schedule in list(get_container().state.schedules.items()):
        if schedule.get("configuration", {}).get("instance_id") == instance_id:
            schedule["enabled"] = False
            get_container().state.schedules[schedule_id] = schedule
    return success(item)


@blueprint.post("/<instance_id>/analyze/<phase>")
@require_user
@resource_mutation
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


def _present(item):
    return {
        **item,
        "strategy": strategy_context(
            get_container(), str(item["owner_id"]), str(item["strategy_version_id"])
        ),
        "notification_channels": [
            {
                "id": row["id"],
                "name": row.get("name") or row["channel"],
                "enabled": row.get("enabled", True),
            }
            for row in get_container().state.subscriptions
            if row["owner_id"] == item["owner_id"]
            and ("subscription_ids" not in item or row["id"] in item["subscription_ids"])
        ],
    }

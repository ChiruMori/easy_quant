from datetime import datetime, timedelta
from decimal import Decimal

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
    portfolio_balances,
    read_portfolio,
    reporting_snapshot,
    termination_snapshot,
    validate_termination_snapshot,
)
from easy_quant.application.services.live_runtime import analyze_live_instance
from easy_quant.application.services.live_schedules import (
    initial_live_schedules,
    is_live_schedule,
    sync_live_schedules,
)
from easy_quant.application.services.manual_operations import ManualCommand, ManualOperationService
from easy_quant.application.services.recommendation_actions import audit_row
from easy_quant.domain.market_data.indices import is_index
from easy_quant.domain.shared.errors import NotFoundError, StateConflictError, ValidationError
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
    get_container().resource_lifecycle.add_live_instance(
        item, initial_live_schedules(get_container(), item)
    )
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
    if any(key in request.args for key in ("page", "page_size", "search", "status")):
        try:
            page, size = int(request.args.get("page", 1)), int(request.args.get("page_size", 20))
        except ValueError as error:
            raise ValidationError("分页参数必须为整数") from error
        status, search = request.args.get("status", ""), request.args.get("search", "").strip()
        if page < 1 or not 1 <= size <= 100 or status not in {"", "active", "paused", "terminated"}:
            raise ValidationError("分页或状态参数无效")
        instances = get_container().state.live_instances
        if hasattr(instances, "page_for_owner"):
            result = instances.page_for_owner(g.current_user.id, page, size, search, status)
        else:
            rows = [
                row
                for row in instances.values()
                if row["owner_id"] == g.current_user.id
                and search.casefold() in str(row.get("name", "")).casefold()
                and (not status or row["status"] == status)
            ]
            rows.sort(
                key=lambda row: (str(row.get("started_at", "")), str(row["id"])), reverse=True
            )
            total = len(rows)
            page = min(page, max(1, (total + size - 1) // size))
            result = {
                "items": rows[(page - 1) * size : page * size],
                "page": page,
                "page_size": size,
                "total": total,
            }
        result["items"] = [_present(row) for row in result["items"]]
        return success(result)
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
        if request.args.get("view") == "summary":
            return success(
                {
                    **_present(item),
                    "operations": operations,
                    "balances": portfolio_balances(snapshot, instance_id),
                }
            )
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
    portfolio = read_portfolio(get_container(), instance_id, g.current_user.id)
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


@blueprint.get("/<instance_id>/portfolio")
@require_user
def live_portfolio(instance_id: str):
    metrics_only = request.args.get("view") == "metrics"
    result = read_portfolio(
        get_container(), instance_id, g.current_user.id, include_curve=not metrics_only
    )
    return success(
        {key: result[key] for key in ("at", "profit", "return_rate")} if metrics_only else result
    )


@blueprint.get("/<instance_id>/deliveries")
@require_user
def live_deliveries(instance_id: str):
    try:
        page = int(request.args.get("page", "1"))
        size = int(request.args.get("page_size", "20"))
    except ValueError as error:
        raise ValidationError("分页参数必须为整数") from error
    if page < 1 or not 1 <= size <= 100:
        raise ValidationError("页码必须为正数，每页 1–100 条")
    container = get_container()
    item = container.state.live_instances.get(instance_id)
    if item is None or item["owner_id"] != g.current_user.id:
        raise NotFoundError("live_instance")
    recommendation_ids = {row["id"] for row in container.state.recommendations.get(instance_id, [])}
    deliveries = container.state.deliveries
    if hasattr(deliveries, "page_for_live"):
        result = deliveries.page_for_live(
            g.current_user.id, instance_id, recommendation_ids, page, size
        )
    else:
        rows = [
            row
            for row in deliveries
            if row.get("owner_id") == g.current_user.id
            and (
                row.get("live_instance_id") == instance_id
                or row.get("event_id") in recommendation_ids
                or str(row.get("event_id", "")).startswith(f"{instance_id}:")
            )
        ]
        rows.sort(key=lambda row: (str(row.get("created_at") or ""), str(row["id"])), reverse=True)
        total = len(rows)
        page = min(page, max(1, (total + size - 1) // size))
        result = {
            "items": rows[(page - 1) * size : page * size],
            "total": total,
            "page": page,
            "page_size": size,
        }
    fields = {
        "id",
        "channel",
        "status",
        "attempts",
        "created_at",
        "updated_at",
        "error",
        "error_code",
    }
    result["items"] = [
        {key: value for key, value in row.items() if key in fields} for row in result["items"]
    ]
    return success(result)


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
    item = _set_status(instance_id, "paused", "pause")
    sync_live_schedules(get_container(), instance_id)
    return success(item)


def _set_status(instance_id: str, status: str, action: str):
    container = get_container()
    snapshot, frozen = (
        termination_snapshot(container, instance_id, g.current_user.id)
        if status == "terminated"
        else (None, None)
    )
    with container.live_tracking.transaction() as state:
        item = state.instances.get(instance_id)
        if item is None or item["owner_id"] != g.current_user.id:
            raise NotFoundError("live_instance")
        previous_status = str(item["status"])
        if previous_status == "terminated":
            if status != "terminated":
                raise StateConflictError("已终止实盘不可恢复或修改")
            return item
        if status == "terminated":
            validate_termination_snapshot(state, instance_id, snapshot)
            assert frozen is not None
            item = {
                **item,
                "terminated_at": frozen["at"],
                "frozen_balances": portfolio_balances(state, instance_id),
                "frozen_portfolio": frozen,
            }
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
    sync_live_schedules(get_container(), instance_id)
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
        **{key: value for key, value in item.items() if key != "frozen_portfolio"},
        **(
            {"return_rate": item["frozen_portfolio"]["return_rate"]}
            if item.get("frozen_portfolio")
            else {}
        ),
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


@blueprint.post("/<instance_id>/resume")
@require_user
@resource_mutation
def resume_live(instance_id: str):
    item = _set_status(instance_id, "active", "resume")
    sync_live_schedules(get_container(), instance_id, create=True)
    return success(item)


@blueprint.get("/<instance_id>/schedules")
@require_user
def live_schedules(instance_id: str):
    container = get_container()
    item = container.state.live_instances.get(instance_id)
    if item is None or item["owner_id"] != g.current_user.id:
        raise NotFoundError("live_instance")
    return success(
        [
            row
            for row in container.state.schedules.values()
            if is_live_schedule(row)
            and row.get("configuration", {}).get("instance_id") == instance_id
        ]
    )


@blueprint.patch("/<instance_id>/schedules/<schedule_id>")
@require_user
@resource_mutation
def update_live_schedule(instance_id: str, schedule_id: str):
    from easy_quant.application.services.scheduled_tasks import next_run
    from easy_quant.domain.scheduling.entities import ScheduledTask, ScheduleKind

    container = get_container()
    instance = container.state.live_instances.get(instance_id)
    row = container.state.schedules.get(schedule_id)
    if (
        instance is None
        or instance["owner_id"] != g.current_user.id
        or row is None
        or not is_live_schedule(row)
        or row.get("configuration", {}).get("instance_id") != instance_id
    ):
        raise NotFoundError("live_schedule")
    if instance["status"] != "paused":
        raise StateConflictError("仅暂停的实盘可修改运行时间")
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) != {"schedule_expression"}:
        raise ValidationError("仅允许修改时间表达式")
    expression = payload["schedule_expression"]
    if not isinstance(expression, str) or not expression.strip() or len(expression) > 120:
        raise ValidationError("请输入有效的五段 Cron 表达式")
    now = container.authentication.clock.now()
    following = next_run(
        ScheduledTask(
            schedule_id,
            "live-analysis",
            ScheduleKind.CRON,
            expression.strip(),
            str(row.get("timezone", "Asia/Shanghai")),
            dict(row["configuration"]),
            now,
        ),
        now,
    )
    updated = {
        **row,
        "schedule_kind": "cron",
        "schedule_expression": expression.strip(),
        "custom_expression": True,
        "next_run_at": following.isoformat(),
        "enabled": False,
    }
    container.state.schedules[schedule_id] = updated
    record_audit(
        container,
        actor_user_id=g.current_user.id,
        action="update",
        resource_type="live_schedule",
        resource_id=schedule_id,
        before={"schedule_expression": row["schedule_expression"]},
        after={"instance_id": instance_id, "schedule_expression": expression.strip()},
    )
    return success(updated)

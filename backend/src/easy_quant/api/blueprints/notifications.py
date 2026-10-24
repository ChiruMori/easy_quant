from flask import Blueprint, g, request

from easy_quant.api.dependencies import get_container
from easy_quant.api.middleware.auth import require_user
from easy_quant.api.resource_lifecycle import delete_resource, inspect_resource, resource_mutation
from easy_quant.api.responses import success
from easy_quant.application.services.audit_runtime import record_audit
from easy_quant.application.services.notification_runtime import notify_owner
from easy_quant.application.services.notification_targets import validate_notification_target
from easy_quant.domain.shared.errors import ValidationError
from easy_quant.infrastructure.core import UuidGenerator

blueprint = Blueprint("notifications", __name__, url_prefix="/api/v1/notifications")


def _page(rows):
    if "page" not in request.args and "page_size" not in request.args:
        return rows
    try:
        page = int(request.args.get("page", 1))
        size = int(request.args.get("page_size", 10))
    except ValueError as error:
        raise ValidationError("分页参数必须为整数") from error
    if page < 1 or not 1 <= size <= 100:
        raise ValidationError("页码必须为正数，每页 1–100 条")
    return {
        "items": rows[(page - 1) * size : page * size],
        "total": len(rows),
        "page": page,
        "page_size": size,
    }


def _public_subscription(item):
    return {key: item.get(key) for key in ("id", "name", "channel", "enabled")} | {
        "destination": "***"
    }


@blueprint.get("/subscriptions/<subscription_id>/deletion-preview")
@require_user
def deletion_preview(subscription_id: str):
    return inspect_resource("subscription", subscription_id)


@blueprint.delete("/subscriptions/<subscription_id>")
@require_user
def delete_subscription(subscription_id: str):
    return delete_resource("subscription", subscription_id)


@blueprint.get("/subscriptions")
@require_user
def subscriptions():
    return success(
        _page(
            [
                _public_subscription(item)
                for item in get_container().state.subscriptions
                if item["owner_id"] == g.current_user.id
            ]
        )
    )


@blueprint.get("/subscriptions/<subscription_id>")
@require_user
def subscription_detail(subscription_id: str):
    item = next(
        (
            row
            for row in get_container().state.subscriptions
            if row["id"] == subscription_id and row["owner_id"] == g.current_user.id
        ),
        None,
    )
    if item is None:
        return success(None, status=404)
    try:
        box = get_container().secret_box
        if box is None:
            raise ValueError("unavailable")
        destination = box.decrypt(item["destination_encrypted"])
        signing_secret = (
            box.decrypt(str(item["signing_secret_encrypted"]))
            if item.get("signing_secret_encrypted")
            else ""
        )
    except Exception:
        raise ValidationError("通知目标无法读取，请重新填写并保存") from None
    response, status = success(
        _public_subscription(item) | {"destination": destination, "signing_secret": signing_secret}
    )
    response.headers["Cache-Control"] = "no-store"
    return response, status


@blueprint.post("/subscriptions")
@require_user
@resource_mutation
def add_subscription():
    payload = request.get_json() or {}
    validate_notification_target(
        payload.get("channel"), payload.get("destination"), payload.get("signing_secret", "")
    )
    name = str(payload.get("name", "")).strip()
    if not name or len(name) > 160 or not str(payload.get("destination", "")).strip():
        raise ValidationError("请填写渠道名称（最多 160 字）和通知目标")
    secret_box = get_container().secret_box
    if secret_box is None:
        raise RuntimeError("通知凭据加密器未配置")
    item = {
        "id": f"subscription-{UuidGenerator().new()}",
        "owner_id": g.current_user.id,
        "name": name,
        "channel": payload.get("channel"),
        "destination_encrypted": secret_box.encrypt(str(payload.get("destination", ""))),
        "enabled": True,
        "signing_secret_encrypted": secret_box.encrypt(payload["signing_secret"])
        if payload.get("signing_secret")
        else None,
    }
    get_container().state.subscriptions.append(item)
    record_audit(
        get_container(),
        actor_user_id=g.current_user.id,
        action="create",
        resource_type="notification_subscription",
        resource_id=str(item["id"]),
        after={"channel": str(item["channel"]), "enabled": True},
    )
    return success(_public_subscription(item), status=201)


@blueprint.get("/deliveries")
@require_user
def deliveries():
    rows = [
        {
            key: item.get(key)
            for key in (
                "id",
                "event_id",
                "channel",
                "status",
                "attempts",
                "created_at",
                "updated_at",
                "last_attempt_at",
                "delivered_at",
                "error",
                "error_code",
            )
        }
        for item in get_container().state.deliveries
        if item.get("owner_id") == g.current_user.id
    ]
    rows.sort(
        key=lambda row: (str(row.get("created_at") or row.get("updated_at") or ""), str(row["id"])),
        reverse=True,
    )
    return success(_page(rows))


@blueprint.patch("/subscriptions/<subscription_id>")
@require_user
@resource_mutation
def update_subscription(subscription_id: str):
    item = next(
        (
            row
            for row in get_container().state.subscriptions
            if row["id"] == subscription_id and row["owner_id"] == g.current_user.id
        ),
        None,
    )
    if item is None:
        return success(None, status=404)
    item = dict(item)
    payload = request.get_json() or {}
    if "name" in payload:
        name = str(payload["name"]).strip()
        if not name or len(name) > 160:
            raise ValidationError("请填写渠道名称（最多 160 字）")
        item["name"] = name
    if "enabled" in payload:
        if not isinstance(payload["enabled"], bool):
            raise ValidationError("启用状态必须为布尔值")
        item["enabled"] = payload["enabled"]
    if "destination" in payload:
        destination = payload["destination"]
        if not isinstance(destination, str) or not destination.strip() or len(destination) > 4096:
            raise ValidationError("请填写有效通知目标（最多 4096 字）")
        box = get_container().secret_box
        if box is None:
            raise ValidationError("通知凭据加密器未配置")
        item["destination_encrypted"] = box.encrypt(destination.strip())
    if "signing_secret" in payload:
        secret = payload["signing_secret"]
        if not isinstance(secret, str) or len(secret) > 512:
            raise ValidationError("签名密钥格式无效")
        box = get_container().secret_box
        if box is None:
            raise ValidationError("通知凭据加密器未配置")
        item["signing_secret_encrypted"] = box.encrypt(secret) if secret else None
    if "destination" in payload or "signing_secret" in payload:
        box = get_container().secret_box
        if box is None:
            raise ValidationError("通知凭据加密器未配置")
        validate_notification_target(
            item["channel"],
            box.decrypt(item["destination_encrypted"]),
            box.decrypt(str(item["signing_secret_encrypted"]))
            if item.get("signing_secret_encrypted")
            else "",
        )
    subscriptions = get_container().state.subscriptions
    index = next(index for index, row in enumerate(subscriptions) if row["id"] == subscription_id)
    subscriptions[index] = item
    record_audit(
        get_container(),
        actor_user_id=g.current_user.id,
        action="update",
        resource_type="notification_subscription",
        resource_id=subscription_id,
        after={"enabled": bool(item["enabled"])},
    )
    return success(_public_subscription(item))


@blueprint.post("/subscriptions/<subscription_id>/test")
@require_user
@resource_mutation
def test_subscription(subscription_id: str):
    item = next(
        (
            row
            for row in get_container().state.subscriptions
            if row["id"] == subscription_id and row["owner_id"] == g.current_user.id
        ),
        None,
    )
    if item is None:
        return success(None, status=404)
    if not item.get("enabled", True):
        raise ValidationError("请先启用该渠道再测试")
    results = notify_owner(
        get_container(),
        g.current_user.id,
        f"test:{UuidGenerator().new()}",
        "Easy Quant 连通性测试",
        "这是一条通知渠道测试消息。",
        [subscription_id],
    )
    return success(
        {
            "status": results[0]["status"],
            "message": "测试消息已发送，请检查接收端"
            if results[0]["status"] == "delivered"
            else "测试未送达，请检查渠道配置",
        }
    )

from flask import Blueprint, g, request

from easy_quant.api.dependencies import get_container
from easy_quant.api.middleware.auth import require_user
from easy_quant.api.responses import success
from easy_quant.application.services.audit_runtime import record_audit
from easy_quant.domain.shared.errors import ValidationError
from easy_quant.infrastructure.core import UuidGenerator

blueprint = Blueprint("notifications", __name__, url_prefix="/api/v1/notifications")


@blueprint.get("/subscriptions")
@require_user
def subscriptions():
    return success(
        [
            {
                **{key: value for key, value in item.items() if key != "destination_encrypted"},
                "destination": "***",
            }
            for item in get_container().state.subscriptions
            if item["owner_id"] == g.current_user.id
        ]
    )


@blueprint.post("/subscriptions")
@require_user
def add_subscription():
    payload = request.get_json() or {}
    if payload.get("channel") not in {"email", "ntfy"}:
        raise ValidationError("通知渠道仅支持邮件或 ntfy")
    secret_box = get_container().secret_box
    if secret_box is None:
        raise RuntimeError("通知凭据加密器未配置")
    item = {
        "id": f"subscription-{UuidGenerator().new()}",
        "owner_id": g.current_user.id,
        "channel": payload.get("channel"),
        "destination_encrypted": secret_box.encrypt(str(payload.get("destination", ""))),
        "enabled": True,
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
    return success({**item, "destination_encrypted": None, "destination": "***"}, status=201)


@blueprint.get("/deliveries")
@require_user
def deliveries():
    return success(
        [
            item
            for item in get_container().state.deliveries
            if item.get("owner_id") == g.current_user.id
        ]
    )


@blueprint.patch("/subscriptions/<subscription_id>")
@require_user
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
    item["enabled"] = bool((request.get_json() or {}).get("enabled", True))
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
    return success(
        {
            **{key: value for key, value in item.items() if key != "destination_encrypted"},
            "destination": "***",
        }
    )

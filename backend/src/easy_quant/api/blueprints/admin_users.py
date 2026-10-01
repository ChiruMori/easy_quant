from datetime import timedelta

from flask import Blueprint, g, request

from easy_quant.api.dependencies import get_container
from easy_quant.api.middleware.auth import require_admin
from easy_quant.api.responses import success
from easy_quant.api.schemas.admin_users import InvitationCreateRequest, UserUpdateRequest
from easy_quant.application.services.audit_runtime import record_audit
from easy_quant.application.services.identity_admin import IdentityAdminService
from easy_quant.domain.identity.entities import UserRole, UserStatus
from easy_quant.domain.shared.errors import NotFoundError, ValidationError
from easy_quant.infrastructure.core import SystemClock, UuidGenerator

blueprint = Blueprint("admin_users", __name__, url_prefix="/api/v1/admin")


def service() -> IdentityAdminService:
    return IdentityAdminService(
        get_container().authentication.repository, SystemClock(), UuidGenerator()
    )


@blueprint.post("/invitations")
@require_admin
def create_invitation():
    payload = InvitationCreateRequest.model_validate(request.get_json() or {})
    invitation, token = service().issue_invitation(
        g.current_user, timedelta(hours=payload.lifetime_hours)
    )
    record_audit(
        get_container(),
        actor_user_id=g.current_user.id,
        action="create",
        resource_type="invitation",
        resource_id=invitation.id,
        after={"expires_at": invitation.expires_at.isoformat()},
    )
    return success(
        {"id": invitation.id, "token": token, "expires_at": invitation.expires_at.isoformat()},
        status=201,
    )


@blueprint.get("/invitations")
@require_admin
def invitations():
    return success(
        [
            {
                "id": item.id,
                "expires_at": item.expires_at.isoformat(),
                "used_at": item.used_at.isoformat() if item.used_at else None,
                "revoked_at": item.revoked_at.isoformat() if item.revoked_at else None,
            }
            for item in get_container().authentication.repository.list_invitations()
        ]
    )


@blueprint.get("/users")
@require_admin
def users():
    return success(
        [
            {"id": user.id, "username": user.username, "role": user.role, "status": user.status}
            for user in service().list_users(g.current_user)
        ]
    )


@blueprint.patch("/users/<user_id>")
@require_admin
def update_user(user_id: str):
    payload = UserUpdateRequest.model_validate(request.get_json() or {})
    item = get_container().authentication.repository.get_user(user_id)
    if item is None:
        raise NotFoundError("user")
    if payload.role is None and payload.status is None:
        raise ValidationError("至少提供 role 或 status")
    if payload.role is not None:
        item = service().set_role(g.current_user, user_id, UserRole(payload.role))
    if payload.status is not None:
        item = service().set_status(g.current_user, user_id, UserStatus(payload.status))
    record_audit(
        get_container(),
        actor_user_id=g.current_user.id,
        action="update",
        resource_type="user",
        resource_id=user_id,
        after={"role": item.role.value, "status": item.status.value},
    )
    return success(
        {"id": item.id, "username": item.username, "role": item.role, "status": item.status}
    )

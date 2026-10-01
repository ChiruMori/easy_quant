from __future__ import annotations

from flask import Blueprint, request, session

from easy_quant.api.dependencies import get_container
from easy_quant.api.middleware.auth import require_user
from easy_quant.api.responses import success
from easy_quant.api.schemas.admin_users import InvitationAcceptRequest
from easy_quant.api.schemas.auth import CredentialsRequest, user_response
from easy_quant.application.services.identity_admin import IdentityAdminService
from easy_quant.infrastructure.core import SystemClock, UuidGenerator

blueprint = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


@blueprint.post("/initialize")
def initialize():
    command = CredentialsRequest.model_validate(request.get_json(silent=True) or {})
    user = get_container().authentication.initialize_admin(command.username, command.password)
    return success(user_response(user), status=201)


@blueprint.post("/login")
def login():
    command = CredentialsRequest.model_validate(request.get_json(silent=True) or {})
    user, credentials = get_container().authentication.login(command.username, command.password)
    session.clear()
    session["session_token"] = credentials.token
    session["csrf_token"] = credentials.csrf_token
    return success({"user": user_response(user), "csrf_token": credentials.csrf_token})


@blueprint.post("/logout")
@require_user
def logout():
    get_container().authentication.logout(session.get("session_token"))
    session.clear()
    return "", 204


@blueprint.get("/me")
@require_user
def me():
    from flask import g

    return success({"user": user_response(g.current_user), "csrf_token": session["csrf_token"]})


@blueprint.post("/accept-invitation")
def accept_invitation():
    payload = InvitationAcceptRequest.model_validate(request.get_json(silent=True) or {})
    authentication = get_container().authentication
    service = IdentityAdminService(authentication.repository, SystemClock(), UuidGenerator())
    user = service.accept_invitation(payload.token, payload.username, payload.password)
    return success(user_response(user), status=201)

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, cast

from flask import g, request, session

from easy_quant.api.dependencies import get_container
from easy_quant.domain.identity.entities import UserRole
from easy_quant.domain.shared.errors import ForbiddenError


def require_user[F: Callable[..., Any]](function: F) -> F:
    @wraps(function)
    def wrapped(*args: object, **kwargs: object):
        user, user_session = get_container().authentication.authenticate(
            session.get("session_token")
        )
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            get_container().authentication.check_csrf(
                user_session, request.headers.get("X-CSRF-Token")
            )
        g.current_user = user
        g.current_session = user_session
        return function(*args, **kwargs)

    return cast(F, wrapped)


def require_admin[F: Callable[..., Any]](function: F) -> F:
    @require_user
    @wraps(function)
    def wrapped(*args: object, **kwargs: object):
        if g.current_user.role is not UserRole.ADMIN:
            raise ForbiddenError()
        return function(*args, **kwargs)

    return cast(F, wrapped)

from __future__ import annotations

import logging

from flask import Flask, g
from pydantic import ValidationError as PydanticValidationError

from easy_quant.api.responses import error_response
from easy_quant.application.errors import AuthenticationRequired, InvalidCredentials
from easy_quant.domain.shared.errors import (
    DomainError,
    ForbiddenError,
    NotFoundError,
    StateConflictError,
)

logger = logging.getLogger(__name__)


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(DomainError)
    def handle_domain_error(error: DomainError):
        status = 400
        if isinstance(error, (AuthenticationRequired, InvalidCredentials)):
            status = 401
        elif isinstance(error, ForbiddenError):
            status = 403
        elif isinstance(error, NotFoundError):
            status = 404
        elif isinstance(error, StateConflictError):
            status = 409
        return error_response(
            error.code,
            error.message,
            details=dict(error.details),
            request_id=getattr(g, "request_id", None),
            status=status,
        )

    @app.errorhandler(PydanticValidationError)
    def handle_schema_error(error: PydanticValidationError):
        return error_response(
            "invalid_request",
            "请求参数无效",
            details={"issues": error.errors(include_url=False)},
            request_id=getattr(g, "request_id", None),
            status=422,
        )

    @app.errorhandler(404)
    def handle_not_found(_error):
        return error_response(
            "not_found", "资源不存在", request_id=getattr(g, "request_id", None), status=404
        )

    @app.errorhandler(Exception)
    def handle_unexpected(error: Exception):
        logger.exception("未处理异常", extra={"request_id": getattr(g, "request_id", None)})
        return error_response(
            "internal_error",
            "服务器处理请求时发生错误",
            request_id=getattr(g, "request_id", None),
            status=500,
        )

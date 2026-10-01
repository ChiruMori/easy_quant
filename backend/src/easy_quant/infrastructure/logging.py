from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any

from flask import Flask, g, request

SENSITIVE_FIELDS = {"password", "token", "csrf_token", "secret", "destination", "api_key"}


def redact(value: Any, key: str = "") -> Any:
    if any(part in key.casefold() for part in SENSITIVE_FIELDS):
        return "***"
    if isinstance(value, Mapping):
        return {str(item_key): redact(item, str(item_key)) for item_key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def structured_log(logger: logging.Logger, event: str, **fields: object) -> None:
    logger.info(json.dumps({"event": event, **redact(fields)}, ensure_ascii=False, default=str))


def register_request_logging(app: Flask) -> None:
    @app.after_request
    def log_request(response):
        structured_log(
            app.logger,
            "http_request",
            request_id=getattr(g, "request_id", None),
            method=request.method,
            path=request.path,
            status=response.status_code,
        )
        return response

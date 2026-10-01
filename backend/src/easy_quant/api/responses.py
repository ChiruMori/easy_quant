from __future__ import annotations

from typing import Any

from flask import Response, jsonify


def success(data: Any = None, *, status: int = 200) -> tuple[Response, int]:
    return jsonify({"data": data}), status


def error_response(
    code: str,
    message: str,
    *,
    details: dict[str, object] | None = None,
    request_id: str | None = None,
    status: int = 400,
) -> tuple[Response, int]:
    return (
        jsonify(
            {
                "error": {"code": code, "message": message, "details": details or {}},
                "request_id": request_id,
            }
        ),
        status,
    )

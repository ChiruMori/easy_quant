from __future__ import annotations

from flask import Flask, g, request


def register_request_context(app: Flask) -> None:
    @app.before_request
    def attach_request_id() -> None:
        candidate = request.headers.get("X-Request-ID", "").strip()
        g.request_id = candidate[:100] if candidate else app.extensions["id_generator"].new()

    @app.after_request
    def expose_request_id(response):
        response.headers["X-Request-ID"] = g.request_id
        return response

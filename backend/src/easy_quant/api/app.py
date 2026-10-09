from __future__ import annotations

from flask import Flask

from easy_quant.api.blueprints.admin_market_data import blueprint as admin_market_data_blueprint
from easy_quant.api.blueprints.admin_scheduling import blueprint as admin_scheduling_blueprint
from easy_quant.api.blueprints.admin_users import blueprint as admin_users_blueprint
from easy_quant.api.blueprints.audit import blueprint as audit_blueprint
from easy_quant.api.blueprints.auth import blueprint as auth_blueprint
from easy_quant.api.blueprints.backtests import blueprint as backtests_blueprint
from easy_quant.api.blueprints.factors import blueprint as factors_blueprint
from easy_quant.api.blueprints.live_tracking import blueprint as live_tracking_blueprint
from easy_quant.api.blueprints.notifications import blueprint as notifications_blueprint
from easy_quant.api.blueprints.recommendations import blueprint as recommendations_blueprint
from easy_quant.api.blueprints.strategies import blueprint as strategies_blueprint
from easy_quant.api.blueprints.strategy_library import blueprint as strategy_library_blueprint
from easy_quant.api.errors import register_error_handlers
from easy_quant.api.middleware.request_context import register_request_context
from easy_quant.bootstrap import Container, build_container
from easy_quant.config import Settings, get_settings
from easy_quant.infrastructure.core import UuidGenerator
from easy_quant.infrastructure.logging import register_request_logging


def create_app(*, settings: Settings | None = None, container: Container | None = None) -> Flask:
    settings = settings or get_settings()
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=settings.secret_key.get_secret_value(),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=settings.session_cookie_secure,
        SESSION_COOKIE_SAMESITE="Lax",
        JSON_AS_ASCII=False,
    )
    app.extensions["easy_quant_container"] = container or build_container(settings)

    @app.teardown_appcontext
    def release_database_session(_error: BaseException | None) -> None:
        database_session = app.extensions["easy_quant_container"].database_session
        if database_session is not None:
            database_session.remove()

    app.extensions["id_generator"] = UuidGenerator()
    register_request_context(app)
    register_request_logging(app)
    register_error_handlers(app)
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(backtests_blueprint)
    app.register_blueprint(factors_blueprint)
    app.register_blueprint(live_tracking_blueprint)
    app.register_blueprint(notifications_blueprint)
    app.register_blueprint(recommendations_blueprint)
    app.register_blueprint(strategies_blueprint)
    app.register_blueprint(strategy_library_blueprint)
    app.register_blueprint(admin_market_data_blueprint)
    app.register_blueprint(admin_scheduling_blueprint)
    app.register_blueprint(admin_users_blueprint)
    app.register_blueprint(audit_blueprint)

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok"}

    return app


def main() -> None:
    create_app().run(host="127.0.0.1", port=5000)

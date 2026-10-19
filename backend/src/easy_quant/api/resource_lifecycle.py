from functools import wraps

from flask import g, request

from easy_quant.api.dependencies import get_container
from easy_quant.api.responses import success
from easy_quant.application.services.recommendation_actions import audit_row
from easy_quant.application.services.resource_lifecycle import ResourceLifecycleService
from easy_quant.infrastructure.core import UuidGenerator


def resource_mutation(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        with get_container().resource_lifecycle.guard():
            # 认证读取可能已建立 REPEATABLE READ 快照；获得锁后重新开始读取事务。
            if get_container().database_session is not None:
                get_container().database_session.rollback()
            return function(*args, **kwargs)

    return guarded


def inspect_resource(kind: str, identifier: str):
    return success(
        ResourceLifecycleService(get_container().resource_lifecycle).inspect(
            kind, identifier, g.current_user.id
        )
    )


def delete_resource(kind: str, identifier: str):
    container = get_container()
    payload = request.get_json(silent=True)
    audit = audit_row(
        UuidGenerator(),
        container.authentication.clock.now(),
        g.current_user.id,
        "delete",
        kind,
        identifier,
        {},
        {"deleted": True},
    )
    return success(
        ResourceLifecycleService(container.resource_lifecycle).delete(
            kind,
            identifier,
            g.current_user.id,
            isinstance(payload, dict) and payload.get("confirmed") is True,
            audit,
        )
    )

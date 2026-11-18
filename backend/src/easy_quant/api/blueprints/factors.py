from datetime import date
from threading import BoundedSemaphore

from flask import Blueprint, request

from easy_quant.api.dependencies import get_container
from easy_quant.api.middleware.auth import require_user
from easy_quant.api.responses import success
from easy_quant.application.services.factor_quick_test import quick_test_factor
from easy_quant.domain.shared.errors import StateConflictError, ValidationError
from easy_quant.factors.registry import build_default_registry

blueprint = Blueprint("factors", __name__, url_prefix="/api/v1/factors")
registry = build_default_registry()
quick_test_slots = BoundedSemaphore(2)


def serialize(item, statistics=None):
    stats = (statistics or {}).get(item.key, {})
    calls, elapsed = stats.get("calls", 0), stats.get("elapsed_ns", 0)
    return {
        "calls": calls,
        "total_ms": elapsed / 1_000_000,
        "average_ms": elapsed / calls / 1_000_000 if calls else None,
        "defaults": dict(item.defaults),
        "integer_parameters": item.integer_parameters,
        "key": item.key,
        "name": item.name,
        "description": item.description,
        "parameters": item.parameters,
        "output": item.output,
        "example": item.example,
        "output_example": item.output_example,
    }


@blueprint.get("")
@require_user
def list_factors():
    statistics = get_container().factor_statistics.snapshot()
    return success([serialize(item, statistics) for item in registry.list()])


@blueprint.get("/<key>")
@require_user
def factor_detail(key: str):
    return success(serialize(registry.get(key)))


@blueprint.post("/<key>/quick-test")
@require_user
def factor_quick_test(key: str):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("parameters"), dict):
        raise ValidationError("请填写因子参数与决策日期")
    try:
        trading_day = date.fromisoformat(str(payload["trading_day"]))
    except (KeyError, ValueError) as error:
        raise ValidationError("决策日期无效") from error
    if not quick_test_slots.acquire(blocking=False):
        raise StateConflictError("因子快测正在繁忙，请稍后重试")
    try:
        return success(quick_test_factor(get_container(), key, payload["parameters"], trading_day))
    finally:
        quick_test_slots.release()

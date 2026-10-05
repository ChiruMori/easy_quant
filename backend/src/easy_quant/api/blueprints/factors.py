from flask import Blueprint

from easy_quant.api.middleware.auth import require_user
from easy_quant.api.responses import success
from easy_quant.factors.registry import build_default_registry

blueprint = Blueprint("factors", __name__, url_prefix="/api/v1/factors")
registry = build_default_registry()


def serialize(item):
    return {
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
    return success([serialize(item) for item in registry.list()])


@blueprint.get("/<key>")
@require_user
def factor_detail(key: str):
    return success(serialize(registry.get(key)))

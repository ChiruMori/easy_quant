from flask import Blueprint

from easy_quant.api.middleware.auth import require_user
from easy_quant.api.responses import success
from easy_quant.strategy_api.catalog import LIBRARY

blueprint = Blueprint("strategy_library", __name__, url_prefix="/api/v1/strategy-library")


@blueprint.get("")
@require_user
def library():
    return success(LIBRARY)

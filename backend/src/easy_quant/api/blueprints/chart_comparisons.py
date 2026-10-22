from flask import Blueprint, g, request

from easy_quant.api.dependencies import get_container
from easy_quant.api.middleware.auth import require_user
from easy_quant.api.responses import success
from easy_quant.application.services.chart_comparisons import (
    comparison_candidates,
    comparison_series,
    search_instruments,
)

blueprint = Blueprint("chart_comparisons", __name__, url_prefix="/api/v1/chart-comparisons")


@blueprint.get("/instruments")
@require_user
def instruments():
    return success(search_instruments(get_container(), request.args.get("search", "")))


@blueprint.get("/backtest/<identifier>/candidates")
@require_user
def candidates(identifier: str):
    return success(
        comparison_candidates(
            get_container(), identifier, g.current_user.id, request.args.get("search", "")
        )
    )


@blueprint.get("/<kind>/<identifier>/series")
@require_user
def series(kind: str, identifier: str):
    return success(
        comparison_series(
            get_container(),
            kind,
            identifier,
            g.current_user.id,
            symbol=request.args.get("symbol", "").strip().lower(),
            other_run_id=request.args.get("backtest_id", ""),
        )
    )

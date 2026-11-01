from datetime import date

from flask import Blueprint, request

from easy_quant.api.dependencies import get_container
from easy_quant.api.middleware.auth import require_user
from easy_quant.api.responses import success

blueprint = Blueprint("market_data", __name__, url_prefix="/api/v1/market-data")


def instrument_response(symbol: str):
    normalized = symbol.strip().lower().zfill(6)
    instrument = get_container().market_data.get_instrument(normalized)
    return success(instrument, status=200 if instrument is not None else 404)


def daily_bars_response(symbol: str):
    normalized = symbol.strip().lower().zfill(6)
    start_day = request.args.get("start_day", type=date.fromisoformat)
    end_day = request.args.get("end_day", type=date.fromisoformat)
    rows = get_container().market_data.list_bars(start_day, end_day, normalized)
    return success(rows[-180:] if start_day is None and end_day is None else rows[-1000:])


@blueprint.get("/instruments/<symbol>")
@require_user
def get_instrument(symbol: str):
    return instrument_response(symbol)


@blueprint.get("/instruments/<symbol>/daily-bars")
@require_user
def get_daily_bars(symbol: str):
    return daily_bars_response(symbol)

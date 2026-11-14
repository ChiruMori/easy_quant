from datetime import date

from flask import Blueprint, request

from easy_quant.api.dependencies import get_container
from easy_quant.api.middleware.auth import require_user
from easy_quant.api.responses import success
from easy_quant.domain.market_data.fundamentals import FIELD_METADATA, FINANCIAL_DATASETS
from easy_quant.domain.shared.errors import ValidationError

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


DETAIL_DATASETS = {
    **FINANCIAL_DATASETS,
    "market-values": "估值与市值",
    "valuation-indicators": "估值指标",
    "pledge-ratios": "股票质押率",
    "sw-industry-memberships": "申万行业归属",
    "security-status": "证券状态与风险",
    "daily-bar-availability": "行情可用性",
}


@blueprint.get("/instruments/<symbol>/reports/<dataset>")
@require_user
def get_report_series(symbol: str, dataset: str):
    from easy_quant.platform_library.financials import visible_versions

    if dataset not in FINANCIAL_DATASETS or dataset == "company-profiles":
        raise ValidationError("不支持的报表数据集")
    container = get_container()
    normalized = symbol.strip().lower().zfill(6)
    if container.market_data.get_instrument(normalized) is None:
        return success(None, status=404)
    now = container.authentication.clock.now()
    rows = container.market_data.record_series(dataset, normalized, now)
    if len(rows) > 5000:
        raise ValidationError("该股票报告版本过多，请使用记录分页查看")
    sources = sorted({row.get("source", "") for row in rows})
    source = request.args.get("source") or (
        "eastmoney" if "eastmoney" in sources else next(iter(sources), "")
    )
    # 同一来源、逻辑记录仅使用当前可见版本；不混加来源和修订版本。
    items = visible_versions([row for row in rows if row.get("source", "") == source])
    return success(
        {
            "items": [
                {
                    key: value
                    for key, value in row.items()
                    if key not in {"raw_fields", "field_labels"}
                }
                for row in items
            ],
            "source": source,
            "sources": sources,
            "as_of": now.isoformat(),
        }
    )


@blueprint.get("/instruments/<symbol>/fundamentals")
@require_user
def get_fundamentals(symbol: str):
    container = get_container()
    normalized = symbol.strip().lower().zfill(6)
    if container.market_data.get_instrument(normalized) is None:
        return success(None, status=404)
    now = container.authentication.clock.now()
    counts = container.market_data.record_counts(normalized, now)
    return success(
        {
            "symbol": normalized,
            "as_of": now.isoformat(),
            "fields": {
                key: {"label": label, "unit": unit} for key, (label, unit) in FIELD_METADATA.items()
            },
            "datasets": [
                {"key": key, "name": name, "count": counts.get(key, 0)}
                for key, name in DETAIL_DATASETS.items()
            ],
        }
    )


@blueprint.get("/instruments/<symbol>/fundamentals/<dataset>")
@require_user
def get_fundamental_records(symbol: str, dataset: str):
    if dataset not in DETAIL_DATASETS:
        raise ValidationError("不支持的股票数据集")
    try:
        page = int(request.args.get("page", "1"))
        size = int(request.args.get("page_size", "10"))
    except ValueError as error:
        raise ValidationError("分页参数必须为整数") from error
    if not 1 <= page <= 100000 or not 1 <= size <= 50:
        raise ValidationError("页码或每页数量超出范围")
    container = get_container()
    normalized = symbol.strip().lower().zfill(6)
    if container.market_data.get_instrument(normalized) is None:
        return success(None, status=404)
    now = container.authentication.clock.now()
    return success(
        {
            "items": container.market_data.record_page(dataset, normalized, now, page, size),
            "total": container.market_data.record_counts(normalized, now).get(dataset, 0),
            "page": page,
            "page_size": size,
        }
    )

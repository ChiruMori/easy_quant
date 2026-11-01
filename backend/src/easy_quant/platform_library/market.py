from __future__ import annotations

from easy_quant.domain.market_data.fundamentals import FINANCIAL_DATASETS
from easy_quant.platform_library.context import FactorContext
from easy_quant.platform_library.financials import visible_versions


def daily_bars(context: FactorContext, parameters: dict[str, object]) -> object:
    return context.read("daily-bars", str(parameters["symbol"]))


def market_value(context: FactorContext, parameters: dict[str, object]) -> object:
    rows = context.read("market-values", str(parameters["symbol"]))
    return rows[-1] if rows else None


def latest_record(context: FactorContext, parameters: dict[str, object]) -> object:
    rows = record_history(context, parameters)
    return rows[-1] if rows else None


def record_history(context: FactorContext, parameters: dict[str, object]):
    dataset = str(parameters["dataset"])
    rows = context.read(dataset, str(parameters["symbol"]))
    return visible_versions(rows) if dataset in FINANCIAL_DATASETS else rows

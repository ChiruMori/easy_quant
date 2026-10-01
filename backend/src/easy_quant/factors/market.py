from __future__ import annotations

from easy_quant.factors.context import FactorContext


def daily_bars(context: FactorContext, parameters: dict[str, object]) -> object:
    return context.read("daily-bars", str(parameters["symbol"]))


def market_value(context: FactorContext, parameters: dict[str, object]) -> object:
    rows = context.read("market-values", str(parameters["symbol"]))
    return rows[-1] if rows else None


def latest_record(context: FactorContext, parameters: dict[str, object]) -> object:
    rows = context.read(str(parameters["dataset"]), str(parameters["symbol"]))
    return rows[-1] if rows else None


def record_history(context: FactorContext, parameters: dict[str, object]) -> object:
    return context.read(str(parameters["dataset"]), str(parameters["symbol"]))

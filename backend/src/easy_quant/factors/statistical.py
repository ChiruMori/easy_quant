from __future__ import annotations

from typing import cast

from easy_quant.factors.context import FactorContext


def expected_return(context: FactorContext, parameters: dict[str, object]) -> object:
    import math

    rows = context.frame("daily-bars", str(parameters["symbol"]))
    if len(rows) < 2:
        return {"available": False, "expected_return": None, "win_rate": None}
    if "close" not in rows or any(not math.isfinite(value) for value in rows["close"]):
        return {"available": False, "reason": "missing_or_non_finite_close"}
    closes = rows["close"]
    if (closes.iloc[:-1] == 0).any():
        return {"available": False, "reason": "zero_denominator"}
    returns = closes.pct_change(fill_method=None).iloc[1:]
    return {
        "available": True,
        "expected_return": float(cast(float, returns.mean())),
        "win_rate": float(cast(float, (returns > 0).mean())),
    }

from __future__ import annotations

import math
from typing import cast

from easy_quant.factors.context import FactorContext
from easy_quant.factors.series import ema


def moving_average(context: FactorContext, parameters: dict[str, object]) -> object:
    window = int(str(parameters.get("window", 5)))
    rows = context.frame("daily-bars", str(parameters["symbol"]))
    if len(rows) and (
        "close" not in rows or any(not math.isfinite(value) for value in rows["close"])
    ):
        return {"available": False, "reason": "missing_or_non_finite_close"}
    if len(rows) < window:
        return {"available": False, "required": window, "actual": len(rows)}
    closes = rows["close"].tail(window)
    return {"available": True, "value": float(cast(float, closes.mean())), "window": window}


def relative_strength_index(context: FactorContext, parameters: dict[str, object]) -> object:
    window = int(str(parameters.get("window", 14)))
    rows = context.frame("daily-bars", str(parameters["symbol"]))
    if len(rows) and (
        "close" not in rows or any(not math.isfinite(value) for value in rows["close"])
    ):
        return {"available": False, "reason": "missing_or_non_finite_close"}
    closes = rows["close"].tolist() if "close" in rows else []
    if len(closes) <= window:
        return {"available": False, "required": window + 1, "actual": len(closes)}
    changes = [current - previous for previous, current in zip(closes, closes[1:], strict=False)]
    recent = changes[-window:]
    gains = sum((max(value, float(0)) for value in recent), float(0)) / window
    losses = sum((max(-value, float(0)) for value in recent), float(0)) / window
    value = float(100) if losses == 0 else float(100) - float(100) / (1 + gains / losses)
    return {"available": True, "value": value, "window": window}


def moving_average_convergence_divergence(
    context: FactorContext, parameters: dict[str, object]
) -> object:
    rows = context.frame("daily-bars", str(parameters["symbol"]))
    if len(rows) and (
        "close" not in rows or any(not math.isfinite(value) for value in rows["close"])
    ):
        return {"available": False, "reason": "missing_or_non_finite_close"}
    closes = rows["close"].tolist() if "close" in rows else []
    slow = int(str(parameters.get("slow", 26)))
    fast = int(str(parameters.get("fast", 12)))
    signal_window = int(str(parameters.get("signal", 9)))
    if len(closes) < slow + signal_window:
        return {"available": False, "required": slow + signal_window, "actual": len(closes)}

    fast_values = ema(closes, float(2) / (fast + 1))
    slow_values = ema(closes, float(2) / (slow + 1))
    differences = [left - right for left, right in zip(fast_values, slow_values, strict=True)]
    signal_values = ema(differences, float(2) / (signal_window + 1))
    return {
        "available": True,
        "dif": differences[-1],
        "dea": signal_values[-1],
        "histogram": (differences[-1] - signal_values[-1]) * 2,
    }

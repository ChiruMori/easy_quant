from __future__ import annotations

from decimal import Decimal

from easy_quant.factors.context import FactorContext


def moving_average(context: FactorContext, parameters: dict[str, object]) -> object:
    window = int(str(parameters.get("window", 5)))
    rows = context.read("daily-bars", str(parameters["symbol"]))
    if len(rows) < window:
        return {"available": False, "required": window, "actual": len(rows)}
    closes = [Decimal(str(row["close"])) for row in rows[-window:]]
    return {"available": True, "value": sum(closes) / window, "window": window}


def relative_strength_index(context: FactorContext, parameters: dict[str, object]) -> object:
    window = int(str(parameters.get("window", 14)))
    rows = context.read("daily-bars", str(parameters["symbol"]))
    closes = [Decimal(str(row["close"])) for row in rows]
    if len(closes) <= window:
        return {"available": False, "required": window + 1, "actual": len(closes)}
    changes = [current - previous for previous, current in zip(closes, closes[1:], strict=False)]
    recent = changes[-window:]
    gains = sum((max(value, Decimal(0)) for value in recent), Decimal(0)) / window
    losses = sum((max(-value, Decimal(0)) for value in recent), Decimal(0)) / window
    value = Decimal(100) if losses == 0 else Decimal(100) - Decimal(100) / (1 + gains / losses)
    return {"available": True, "value": value, "window": window}


def moving_average_convergence_divergence(
    context: FactorContext, parameters: dict[str, object]
) -> object:
    rows = context.read("daily-bars", str(parameters["symbol"]))
    closes = [Decimal(str(row["close"])) for row in rows]
    slow = int(str(parameters.get("slow", 26)))
    fast = int(str(parameters.get("fast", 12)))
    signal_window = int(str(parameters.get("signal", 9)))
    if len(closes) < slow + signal_window:
        return {"available": False, "required": slow + signal_window, "actual": len(closes)}

    def ema(values: list[Decimal], window: int) -> list[Decimal]:
        multiplier = Decimal(2) / Decimal(window + 1)
        result = [values[0]]
        for value in values[1:]:
            result.append((value - result[-1]) * multiplier + result[-1])
        return result

    fast_values, slow_values = ema(closes, fast), ema(closes, slow)
    differences = [left - right for left, right in zip(fast_values, slow_values, strict=True)]
    signal_values = ema(differences, signal_window)
    return {
        "available": True,
        "dif": differences[-1],
        "dea": signal_values[-1],
        "histogram": (differences[-1] - signal_values[-1]) * 2,
    }

from __future__ import annotations

from decimal import Decimal

from easy_quant.factors.context import FactorContext


def expected_return(context: FactorContext, parameters: dict[str, object]) -> object:
    rows = context.read("daily-bars", str(parameters["symbol"]))
    closes = [Decimal(str(row["close"])) for row in rows]
    if len(closes) < 2:
        return {"available": False, "expected_return": None, "win_rate": None}
    returns = [
        (current / previous) - 1 for previous, current in zip(closes, closes[1:], strict=False)
    ]
    wins = sum(value > 0 for value in returns)
    return {
        "available": True,
        "expected_return": sum(returns) / len(returns),
        "win_rate": Decimal(wins) / len(returns),
    }

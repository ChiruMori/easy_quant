from __future__ import annotations

from decimal import Decimal


def calculate_metrics(
    equities: list[Decimal],
    turnover: Decimal,
    trade_count: int,
    benchmark_return: Decimal | None = None,
) -> dict[str, Decimal | int | None]:
    if len(equities) < 2 or equities[0] == 0:
        return {
            "cumulative_return": Decimal(0),
            "annualized_return": Decimal(0),
            "max_drawdown": Decimal(0),
            "volatility": Decimal(0),
            "risk_adjusted_return": None,
            "turnover": turnover,
            "trade_count": trade_count,
            "benchmark_return": benchmark_return,
        }
    returns = [
        equities[index] / equities[index - 1] - Decimal(1)
        for index in range(1, len(equities))
        if equities[index - 1] != 0
    ]
    cumulative = equities[-1] / equities[0] - Decimal(1)
    annualized = Decimal(str((1 + float(cumulative)) ** (252 / len(returns)) - 1))
    peak, drawdown = equities[0], Decimal(0)
    for equity in equities:
        peak = max(peak, equity)
        if peak:
            drawdown = min(drawdown, equity / peak - Decimal(1))
    mean = sum(returns, Decimal(0)) / len(returns)
    variance = sum(((value - mean) ** 2 for value in returns), Decimal(0)) / len(returns)
    volatility = Decimal(str(float(variance) ** 0.5)) * Decimal(str(252**0.5))
    adjusted = annualized / volatility if volatility else None
    return {
        "cumulative_return": cumulative,
        "annualized_return": annualized,
        "max_drawdown": drawdown,
        "volatility": volatility,
        "risk_adjusted_return": adjusted,
        "turnover": turnover,
        "trade_count": trade_count,
        "benchmark_return": benchmark_return,
    }

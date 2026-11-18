"""float 时间序列算子。缺失、零分母和退化样本始终显式失败。"""

import math
from collections.abc import Callable, Sequence


class Unavailable(Exception):
    pass


def number(value: object) -> float:
    try:
        result = float(str(value))
    except Exception as error:
        raise Unavailable("missing_field") from error
    if not math.isfinite(result):
        raise Unavailable("non_finite_input")
    return result


def divide(left: float, right: float) -> float:
    if right == 0:
        raise Unavailable("zero_denominator")
    return left / right


def tail(values: Sequence[float], window: int) -> list[float]:
    if len(values) < window:
        raise Unavailable("insufficient_history")
    return list(values[-window:])


def mean(values: Sequence[float]) -> float:
    if len(values) == 0:
        raise Unavailable("insufficient_history")
    import numpy as np

    return float(np.mean(values, dtype=np.float64))


def variance(values: Sequence[float]) -> float:
    if len(values) == 0:
        raise Unavailable("insufficient_history")
    import numpy as np

    return float(np.var(values, dtype=np.float64, ddof=0))


def std(values: Sequence[float]) -> float:
    return math.sqrt(variance(values))


def covariance(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise Unavailable("unaligned_dates")
    a, b = mean(left), mean(right)
    return mean([(x - a) * (y - b) for x, y in zip(left, right, strict=True)])


def regression(y: Sequence[float], x: Sequence[float]) -> tuple[float, float]:
    beta = divide(covariance(y, x), variance(x))
    return mean(y) - beta * mean(x), beta


def returns(values: Sequence[float]) -> list[float]:
    if any(value == 0 for value in values[:-1]):
        raise Unavailable("zero_denominator")
    import pandas as pd

    return pd.Series(values, dtype="float64").pct_change(fill_method=None).iloc[1:].tolist()


def ema(values: Sequence[float], alpha: float) -> list[float]:
    if len(values) == 0:
        raise Unavailable("insufficient_history")
    import pandas as pd

    return pd.Series(values, dtype="float64").ewm(alpha=alpha, adjust=False).mean().tolist()


def percentile(value: float, sample: Sequence[float]) -> float:
    # 平均并列秩 / N；不把时间序列排名当截面排名。
    below = sum(item < value for item in sample)
    equal = sum(item == value for item in sample)
    return (float(below) + float(equal + 1) / 2) / len(sample)


def rolling(values: Sequence[float], window: int, function: Callable) -> list[float]:
    return [function(values[index - window : index]) for index in range(window, len(values) + 1)]

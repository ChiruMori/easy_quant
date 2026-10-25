"""Decimal 时间序列算子。缺失、零分母和退化样本始终显式失败。"""

from collections.abc import Callable, Sequence
from decimal import Decimal


class Unavailable(Exception):
    pass


def number(value: object) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as error:
        raise Unavailable("missing_field") from error
    if not result.is_finite():
        raise Unavailable("non_finite_input")
    return result


def divide(left: Decimal, right: Decimal) -> Decimal:
    if right == 0:
        raise Unavailable("zero_denominator")
    return left / right


def tail(values: Sequence[Decimal], window: int) -> list[Decimal]:
    if len(values) < window:
        raise Unavailable("insufficient_history")
    return list(values[-window:])


def mean(values: Sequence[Decimal]) -> Decimal:
    if not values:
        raise Unavailable("insufficient_history")
    return sum(values, Decimal(0)) / len(values)


def variance(values: Sequence[Decimal]) -> Decimal:
    center = mean(values)
    return mean([(value - center) ** 2 for value in values])


def std(values: Sequence[Decimal]) -> Decimal:
    return variance(values).sqrt()


def covariance(left: Sequence[Decimal], right: Sequence[Decimal]) -> Decimal:
    if len(left) != len(right):
        raise Unavailable("unaligned_dates")
    a, b = mean(left), mean(right)
    return mean([(x - a) * (y - b) for x, y in zip(left, right, strict=True)])


def regression(y: Sequence[Decimal], x: Sequence[Decimal]) -> tuple[Decimal, Decimal]:
    beta = divide(covariance(y, x), variance(x))
    return mean(y) - beta * mean(x), beta


def returns(values: Sequence[Decimal]) -> list[Decimal]:
    return [divide(b, a) - 1 for a, b in zip(values, values[1:], strict=False)]


def ema(values: Sequence[Decimal], alpha: Decimal) -> list[Decimal]:
    if not values:
        raise Unavailable("insufficient_history")
    result = [values[0]]
    for value in values[1:]:
        result.append(alpha * value + (1 - alpha) * result[-1])
    return result


def percentile(value: Decimal, sample: Sequence[Decimal]) -> Decimal:
    # 平均并列秩 / N；不把时间序列排名当截面排名。
    below = sum(item < value for item in sample)
    equal = sum(item == value for item in sample)
    return (Decimal(below) + Decimal(equal + 1) / 2) / len(sample)


def rolling(values: Sequence[Decimal], window: int, function: Callable) -> list[Decimal]:
    return [function(values[index - window : index]) for index in range(window, len(values) + 1)]

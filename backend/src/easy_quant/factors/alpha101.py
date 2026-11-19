"""公开列出的 Alpha101 公式；平台内组合算子，不执行公式字符串。"""

import math
from collections.abc import Callable
from operator import add, mul, sub

from easy_quant.factors.series import (
    Unavailable,
    divide,
    mean,
    number,
    percentile,
    std,
)
from easy_quant.platform_library.context import FactorContext


class Frame:
    """日期为行、证券为列的 float64 DataFrame；NaN 表示不可用。"""

    def __init__(self, values) -> None:
        import pandas as pd

        self.data = pd.DataFrame(values, dtype="float64")

    @property
    def values(self):
        return {
            s: [None if not math.isfinite(v) else float(v) for v in self.data[s]]
            for s in self.data.columns
        }

    def unary(self, function: Callable) -> "Frame":
        def apply(value):
            if not math.isfinite(value):
                return float("nan")
            try:
                result = function(float(value))
                return result if math.isfinite(result) else float("nan")
            except (Unavailable, ArithmeticError, ValueError):
                return float("nan")

        return Frame(self.data.map(apply))

    def binary(self, other: object, function: Callable) -> "Frame":
        right = other.data if isinstance(other, Frame) else number(other)
        result = function(self.data, right) if function is not divide else self.data / right
        return Frame(result.replace([float("inf"), -float("inf")], float("nan")))

    def __add__(self, other):
        return self.binary(other, add)

    __radd__ = __add__

    def __sub__(self, other):
        return self.binary(other, sub)

    def __rsub__(self, other):
        return Frame(number(other) - self.data)

    def __mul__(self, other):
        return self.binary(other, mul)

    __rmul__ = __mul__

    def __truediv__(self, other):
        return self.binary(other, divide)

    def __pow__(self, exponent):
        return Frame(self.data ** number(exponent))

    def __neg__(self):
        return Frame(-self.data)

    def delay(self, window: int):
        return Frame(self.data.shift(window))

    def delta(self, window: int):
        return Frame(self.data.diff(window))

    def roll(self, window: int, function: Callable):
        return Frame(
            self.data.rolling(window, min_periods=window).apply(
                lambda values: function(values.tolist()), raw=False
            )
        )

    def cov(self, other, window):
        return Frame(self.data.rolling(window, min_periods=window).cov(other.data, ddof=0))

    def rank(self):
        return Frame(self.data.rank(axis=1, method="average", pct=True))

    def sign(self):
        return self.unary(lambda v: float((v > 0) - (v < 0)))

    def abs(self):
        return Frame(self.data.abs())

    def ts_rank(self, window):
        return self.roll(window, lambda vs: percentile(vs[-1], vs))

    def corr(self, other, window):
        # 与旧约定一致：完整窗口、总体相关系数，零方差不可用。
        return Frame(
            self.data.rolling(window, min_periods=window)
            .corr(other.data)
            .replace([float("inf"), -float("inf")], float("nan"))
        )

    def choose(self, yes: "Frame", no: "Frame"):
        return Frame(yes.data.where(self.data != 0, no.data).where(self.data.notna()))


ALPHA_NUMBERS = (
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    15,
    16,
    17,
    18,
    19,
    20,
    22,
    23,
    25,
    33,
    34,
    41,
    52,
    53,
    54,
    57,
    101,
)
SINGLE_SYMBOL = {6, 7, 9, 12, 23, 41, 53, 54, 101}


def calculate_alpha(context: FactorContext, parameters: dict[str, object], index: int) -> object:
    symbol = str(parameters["symbol"])
    raw_symbols = parameters.get("symbols")
    if index not in SINGLE_SYMBOL and (
        not isinstance(raw_symbols, list) or symbol not in raw_symbols or len(set(raw_symbols)) < 2
    ):
        return {"available": False, "reason": "explicit_universe_required"}
    symbols = (
        sorted(set(str(s) for s in raw_symbols))
        if isinstance(raw_symbols, list) and index not in SINGLE_SYMBOL
        else [symbol]
    )
    if len(symbols) > 500:
        return {"available": False, "reason": "universe_limit_500"}
    rows = {s: context.read("daily-bars", s) for s in symbols}
    dates = sorted(
        {str(row["trading_day"]) for vs in rows.values() for row in vs if row.get("trading_day")}
    )
    if not dates:
        return {"available": False, "reason": "missing_dated_bars"}
    by_day = {s: {str(row.get("trading_day")): row for row in vs} for s, vs in rows.items()}

    def field(name):
        def value(row):
            try:
                if name == "volume" and row.get("adjusted_volume") is not None:
                    return number(row["adjusted_volume"])
                return number(row.get(name))
            except Unavailable:
                return None

        return Frame({s: [value(by_day[s].get(day, {})) for day in dates] for s in symbols})

    o, h, low, c, v = (field(name) for name in ("open", "high", "low", "close", "volume"))
    r = c / c.delay(1) - 1
    adv = v.roll(20, mean)
    # 成交量以股、成交额以元归一；缺成交额不以典型价冒充 VWAP。
    # 复权价使用同尺度 VWAP；原始成交额不随价格复权变造。
    vw = (
        field("adjusted_vwap")
        if any(row.get("price_scale") is not None for values in rows.values() for row in values)
        else field("amount") / v
    )
    d = c.delta(1)

    def conditional_delta(window):
        positive = d.roll(window, min).unary(lambda x: float(x > 0))
        negative = d.roll(window, max).unary(lambda x: float(x < 0))
        return positive.choose(d, negative.choose(d, -d))

    def formula():
        if index == 1:
            x = r.unary(lambda x: float(x < 0)).choose(r.roll(20, std), c)
            return (x**2).roll(5, lambda vs: float(vs.index(max(vs)) + 1)).rank() - float(".5")
        if index == 2:
            return -v.unary(lambda x: math.log(x)).delta(2).rank().corr(((c - o) / o).rank(), 6)
        if index == 3:
            return -o.rank().corr(v.rank(), 10)
        if index == 4:
            return -low.rank().ts_rank(9)
        if index == 5:
            return (o - vw.roll(10, mean)).rank() * -(c - vw).rank().abs()
        if index == 6:
            return -o.corr(v, 10)
        if index == 7:
            x = -c.delta(7).abs().ts_rank(60) * c.delta(7).sign()
            return (v - adv).unary(lambda x: float(x > 0)).choose(x, c.unary(lambda _: float(-1)))
        if index == 8:
            x = o.roll(5, sum) * r.roll(5, sum)
            return -x.delta(10).rank()
        if index in (9, 10):
            x = conditional_delta(5 if index == 9 else 4)
            return x.rank() if index == 10 else x
        if index == 11:
            return ((vw - c).roll(3, max).rank() + (vw - c).roll(3, min).rank()) * v.delta(3).rank()
        if index == 12:
            return v.delta(1).sign() * -d
        if index in (13, 16):
            return -((c if index == 13 else h).rank().cov(v.rank(), 5)).rank()
        if index == 14:
            return -r.delta(3).rank() * o.corr(v, 10)
        if index == 15:
            return -h.rank().corr(v.rank(), 3).rank().roll(3, sum)
        if index == 17:
            return -c.ts_rank(10).rank() * d.delta(1).rank() * (v / adv).ts_rank(5).rank()
        if index == 18:
            return -((c - o).abs().roll(5, std) + (c - o) + c.corr(o, 10)).rank()
        if index == 19:
            x = ((vw - c).rank().corr(v.rank(), 12) * c.rank().corr(adv.rank(), 12).rank()).rank()
            return (
                -(c - c.delay(7) + c.delta(7)).sign() * (1 + (1 + r.roll(250, sum)).rank()) - x * x
            )
        if index == 20:
            return -(o - h.delay(1)).rank() * (o - c.delay(1)).rank() * (o - low.delay(1)).rank()
        if index == 22:
            return -h.corr(v, 5).delta(5) * c.roll(20, std).rank()
        if index == 23:
            return (
                (h - h.roll(20, mean))
                .unary(lambda x: float(x > 0))
                .choose(-h.delta(2), c.unary(lambda _: float(0)))
            )
        if index == 25:
            return (-r * adv * vw * (h - c)).rank()
        if index == 33:
            return (o / c - 1).rank()
        if index == 34:
            return (1 - (r.roll(2, std) / r.roll(5, std)).rank() + 1 - d.rank()).rank()
        if index == 41:
            return (h * low).unary(lambda x: math.sqrt(x)) - vw
        if index == 52:
            x = low.roll(5, min)
            return (
                (-x + x.delay(5))
                * ((r.roll(240, sum) - r.roll(20, sum)) / 220).rank()
                * v.ts_rank(5)
            )
        if index == 53:
            return -(((c - low) - (h - c)) / (c - low)).delta(9)
        if index == 54:
            return -(low - c) * (o**5) / ((low - h) * (c**5))
        if index == 57:
            x = c.roll(30, lambda vs: float(vs.index(max(vs)) + 1)).rank()
            return -(c - vw) / x.roll(2, lambda vs: (vs[0] + 2 * vs[1]) / 3)
        return (c - o) / (h - low + float(".001"))

    result = formula().values.get(symbol, [])
    value = result[-1] if result else None
    if value is None:
        return {"available": False, "reason": "missing_window_or_undefined_value"}
    return {"available": True, "value": value, "trading_day": dates[-1], "universe": symbols}

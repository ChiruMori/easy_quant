"""公开对标清单中可由现有平台数据支持的因子。"""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal, DecimalException
from functools import partial

from easy_quant.domain.shared.errors import ValidationError
from easy_quant.factors.alpha101 import ALPHA_NUMBERS, calculate_alpha
from easy_quant.factors.series import (
    Unavailable,
    divide,
    ema,
    mean,
    number,
    regression,
    returns,
    rolling,
    std,
    tail,
)
from easy_quant.platform_library.context import FactorContext
from easy_quant.platform_library.types import FactorDefinition


@dataclass(frozen=True)
class Reference:
    key: str
    category: str
    history: int
    function: Callable
    description: str
    datasets: tuple[str, ...] = ("daily-bars",)


def bars(context, symbol):
    rows = context.read("daily-bars", symbol)
    return sorted(rows, key=lambda row: str(row.get("trading_day", "")))


def column(rows, name):
    return [number(row.get(name)) for row in rows]


def calculate(
    context: FactorContext,
    parameters: dict[str, object],
    *,
    operation: str,
    window: int = 1,
    benchmark: str = "sh000300",
) -> Decimal:
    symbol = str(parameters["symbol"])
    rows = bars(context, symbol)
    if operation in {"size", "float_size", "nl_size"}:

        def size(s, field="market_cap"):
            records = context.read("market-values", s)
            if not records:
                raise Unavailable("missing_market_value")
            value = number(records[-1].get(field))
            if value <= 0:
                raise Unavailable("non_positive_market_value")
            return -(value / Decimal(1000000)).ln()

        if operation != "nl_size":
            return size(
                symbol, "circulating_market_cap" if operation == "float_size" else "market_cap"
            )
        symbols = parameters.get("symbols")
        if not isinstance(symbols, list) or symbol not in symbols or len(set(symbols)) < 3:
            raise Unavailable("explicit_universe_at_least_3_required")
        if len(symbols) > 500:
            raise Unavailable("universe_limit_500")
        # 缺失成员不静默删除，以免无声改变中性化股票池。
        x = [size(s) for s in sorted(set(symbols))]
        intercept, beta = regression([value**3 for value in x], x)
        value = size(symbol)
        return value**3 - intercept - beta * value
    required = (
        window + 1 if operation in {"return", "return_std", "sharpe", "adjusted_sharpe"} else window
    )
    if len(rows) < required:
        raise Unavailable("insufficient_history")
    c = column(rows, "close")
    if operation == "return":
        return divide(c[-1], c[-window - 1]) - 1
    if operation == "ma":
        return mean(tail(c, window))
    if operation in {"return_std", "sharpe", "adjusted_sharpe"}:
        r = returns(tail(c, window + 1))
        if operation == "return_std":
            return std(r)
        return divide(mean(r), std(r) ** (4 if operation == "adjusted_sharpe" else 1))
    if operation == "high_low":
        sample = tail(c, window)
        return divide(max(sample), min(sample))
    if operation == "log_price":
        if c[-1] <= 0:
            raise Unavailable("non_positive_price")
        return c[-1].ln()
    if operation == "amount_ma":
        return mean(column(rows[-window:], "amount"))
    if operation == "abs_return_amount":
        r = returns(tail(c, window + 1))
        return divide(
            sum(map(abs, r), Decimal(0)), sum(column(rows[-window:], "amount"), Decimal(0))
        )
    if operation == "price_position_ir":
        ratios = [
            divide(
                number(row.get("close")) - number(row.get("open")),
                number(row.get("high")) - number(row.get("low")),
            )
            for row in rows[-window:]
        ]
        return divide(mean(ratios), std(ratios))
    if operation in {"MACD", "dif", "dea"}:
        if len(c) < 35:
            raise Unavailable("insufficient_history")
        fast, slow = ema(c, Decimal(2) / 13), ema(c, Decimal(2) / 27)
        dif = [a - b for a, b in zip(fast, slow, strict=True)]
        dea = ema(dif, Decimal(2) / 10)
        return {"MACD": 2 * (dif[-1] - dea[-1]), "dif": dif[-1], "dea": dea[-1]}[operation]
    if operation == "rsi":
        changes = [b - a for a, b in zip(c, c[1:], strict=False)]
        if len(changes) < 14:
            raise Unavailable("insufficient_history")
        # Wilder com=period-1, adjust=False, 首个变化为种子；不使用简单移动平均。
        gain = ema([max(v, Decimal(0)) for v in changes], Decimal(1) / 14)[-1]
        loss = ema([max(-v, Decimal(0)) for v in changes], Decimal(1) / 14)[-1]
        if gain == loss == 0:
            raise Unavailable("zero_denominator")
        return Decimal(100) if loss == 0 else 100 - 100 / (1 + gain / loss)
    if operation == "price_dist":
        price = c[-1]
        if price <= 0:
            raise Unavailable("non_positive_price")
        scaled = price / (1 if price < 10 else 10 if price < 100 else 100)
        return scaled.to_integral_value(rounding=ROUND_FLOOR) + 1 - scaled
    if operation == "days_down_up":
        if len(c) < 2:
            raise Unavailable("insufficient_history")
        up = down = 0
        sign = (c[-1] > c[-2]) - (c[-1] < c[-2])
        for a, b in reversed(list(zip(c, c[1:], strict=False))):
            if (b > a) - (b < a) != sign or sign == 0:
                break
            up += int(sign > 0)
            down += int(sign < 0)
        return Decimal(abs(up - down - 1))
    if operation == "days_beyond":
        # 每日滚动 Z 后再在窗口内计数，所需输入为 2w-1 条。
        samples = tail(c, 2 * window - 1)
        zs = [
            divide(
                samples[i + window - 1] - mean(samples[i : i + window]),
                std(samples[i : i + window]),
            )
            for i in range(window)
        ]
        return Decimal(sum(z > 1 for z in zs) - sum(z < -1 for z in zs))
    if operation == "rsrs":
        sample = rows[-217:]
        if len(sample) < 217:
            raise Unavailable("insufficient_history")
        h, low = column(sample, "high"), column(sample, "low")
        # 严格遵循参考页 Low ~ High 的回归方向。
        slopes = [regression(low[i : i + 18], h[i : i + 18])[1] for i in range(200)]
        return divide(slopes[-1] - mean(slopes), std(slopes))
    if operation in {"alpha", "beta", "sigma", "beta_consistency", "volume_alpha", "volume_beta"}:
        volume = operation.startswith("volume_")
        needed = window + (5 if volume else 1)
        stock, index = rows[-needed:], bars(context, benchmark)[-needed:]
        if len(stock) < needed or len(index) < needed:
            raise Unavailable("insufficient_benchmark_history")
        stock_days = [row.get("trading_day") for row in stock]
        index_days = [row.get("trading_day") for row in index]
        if any(day is None for day in stock_days) or stock_days != index_days:
            raise Unavailable("unaligned_dates")
        field = "volume" if volume else "close"
        y, x = column(stock, field), column(index, field)
        if volume:
            y, x = rolling(y, 5, sum), rolling(x, 5, sum)
        y, x = returns(y), returns(x)
        intercept, beta = regression(y, x)
        if operation.endswith("alpha"):
            return intercept
        if operation.endswith("beta"):
            return beta
        residuals = [a - intercept - beta * b for a, b in zip(y, x, strict=True)]
        return std([beta * r for r in residuals] if operation == "beta_consistency" else residuals)
    raise ValueError(f"未注册的计算操作：{operation}")


def execute(context, parameters, *, function):
    extra = parameters.keys() - {"symbol", "symbols"}
    if extra:
        raise ValidationError("对标因子采用Key对应的固定参数", {"fields": sorted(extra)})
    symbols = parameters.get("symbols")
    if symbols is not None and (
        not isinstance(symbols, list) or not all(isinstance(s, str) for s in symbols)
    ):
        raise ValidationError("symbols 必须为证券代码字符串列表")
    try:
        value = function(context, parameters)
        if isinstance(value, dict):
            return value
        if not value.is_finite():
            raise Unavailable("non_finite_result")
        return {"available": True, "value": value}
    except Unavailable as error:
        return {"available": False, "reason": str(error)}
    except DecimalException:
        return {"available": False, "reason": "undefined_numeric_result"}


def references() -> tuple[Reference, ...]:
    result: list[Reference] = []
    descriptions = {
        "return": "窗口累计收益率：末日收盘价/窗口前收盘价-1",
        "ma": "窗口收盘价的算术均值",
        "price_position_ir": "日内(收盘-开盘)/(最高-最低)的窗口均值/总体标准差",
        "alpha": "股票日收益对指数日收益含截距回归的截距",
        "beta": "股票日收益对指数日收益含截距回归的斜率",
        "sigma": "股票日收益对指数回归后残差的总体标准差",
        "beta_consistency": "股票对指数回归的Beta乘残差后的总体标准差",
        "volume_alpha": "五日累计成交量变化率对指数同口径变化率回归的截距",
        "volume_beta": "五日累计成交量变化率对指数同口径变化率回归的斜率",
        "rsrs": "18日Low对High回归斜率，再以200个斜率计算Z值",
        "MACD": "12/26日EMA差值减9日信号EMA后乘2",
        "dif": "12日EMA减26日EMA",
        "dea": "12/26日EMA差值的9日EMA",
        "days_down_up": "连续上涨天数减连续下跌天数再减1的绝对值",
        "amount_ma": "窗口成交额（元）的算术均值",
        "abs_return_amount": "窗口绝对日收益之和/窗口成交额之和",
        "rsi": "14日Wilder递归平滑的相对强弱指标",
        "price_dist": "价格按1/10/100缩放后距离下一个整数的差",
        "days_beyond": "每日滚动Z值大于1与小于-1的窗口天数之差",
        "return_std": "窗口日收益的总体标准差",
        "high_low": "窗口累计净值最高/最低之比，等价于同口径收盘价最高/最低",
        "sharpe": "窗口日收益均值/总体标准差，不年化、不扣无风险利率",
        "adjusted_sharpe": "窗口日收益均值/总体标准差的四次方",
        "log_price": "收盘价的自然对数",
        "size": "最新可见总市值（元）除以百万后取负自然对数",
        "float_size": "最新可见流通市值（元）除以百万后取负自然对数",
        "nl_size": "显式股票池内Size三次方对Size含截距回归的残差",
    }

    def add(
        key, category, operation, history, window=1, benchmark="sh000300", datasets=("daily-bars",)
    ):
        result.append(
            Reference(
                key,
                category,
                history,
                partial(calculate, operation=operation, window=window, benchmark=benchmark),
                f"{descriptions[operation]}；默认预热{history}个交易日，指数项使用{benchmark}。",
                datasets,
            )
        )

    for n in ALPHA_NUMBERS:
        result.append(
            Reference(
                f"alpha101_{n}",
                "Alpha101",
                300,
                partial(calculate_alpha, index=n),
                f"Alpha101 第 {n} 项；截面项必须显式指定 symbols。",
            )
        )
    for w in (5, 21, 42, 63, 126, 252):
        add(f"return_{w}d", "Momentum", "return", w + 1, w)
    add("ma_20d", "Momentum", "ma", 20, 20)
    add("price_position_ir_60d", "Momentum", "price_position_ir", 60, 60)
    for w, b in (
        (125, "000300"),
        (250, "000300"),
        (500, "000300"),
        (528, "000001"),
        (792, "000001"),
        (1000, "000300"),
        (1320, "000001"),
    ):
        add(f"alpha_{w}d_{b}", "Momentum", "alpha", w + 1, w, "sh" + b)
    add("rsrs", "Momentum", "rsrs", 217)
    for key in ("MACD", "dif", "dea"):
        add(key, "Momentum", key, 250)
    add("days_down_up", "Momentum", "days_down_up", 250)
    add("amount_ma_20d", "Liquidity", "amount_ma", 20, 20)
    add("sum_abs_rtn_amount_20d", "Liquidity", "abs_return_amount", 21, 20)
    for b in ("000001", "000300"):
        add(f"volume_alpha_300d_{b}", "Liquidity", "volume_alpha", 305, 300, "sh" + b)
    add("rsi", "Reversal", "rsi", 250)
    add("price_dist", "Reversal", "price_dist", 1)
    add("days_beyond_upper_lower_21d", "Risk", "days_beyond", 41, 21)
    for w in (21, 42, 63, 126, 252):
        add(f"return_std_{w}d", "Risk", "return_std", w + 1, w)
        add(f"high_low_{w}d", "Risk", "high_low", w, w)
    for w in (60, 750):
        add(f"sharpe_{w}d", "Risk", "sharpe", w + 1, w)
    add("adjusted_sharpe_750d", "Risk", "adjusted_sharpe", 751, 750)
    for w, b in (
        (60, "000300"),
        (125, "000300"),
        (250, "000300"),
        (500, "000300"),
        (1000, "000300"),
        (1320, "000001"),
    ):
        add(f"beta_{w}d_{b}", "Risk", "beta", w + 1, w, "sh" + b)
    add("volume_beta_120d_000300", "Risk", "volume_beta", 125, 120)
    for b in ("000001", "000300"):
        add(f"sigma_1320d_{b}", "Risk", "sigma", 1321, 1320, "sh" + b)
    add("beta_consistency_1320d_000300", "Risk", "beta_consistency", 1321, 1320)
    add("log_price", "Risk", "log_price", 1)
    for key in ("size", "float_size", "nl_size"):
        add(key, "Size", key, 1, datasets=("market-values",))
    return tuple(result)


def definitions() -> tuple[FactorDefinition, ...]:
    return tuple(
        FactorDefinition(
            key=item.key,
            name=item.key,
            description=item.description,
            parameters={"symbol": "证券代码", "symbols": "截面项必传的显式股票池；其余可省略"},
            defaults={"symbols": None},
            output="{'available': True, 'value': Decimal} 或 {'available': False, 'reason': str}",
            example=(
                f"context.factor('{item.key}', symbol='000001', "
                "symbols=['000001', '000002', '000003'])"
            ),
            output_example="{'available': True, 'value': Decimal('0.1')}",
            function=partial(execute, function=item.function),
            datasets=item.datasets,
            required_history=item.history,
        )
        for item in references()
    )

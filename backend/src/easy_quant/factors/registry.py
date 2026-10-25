from __future__ import annotations

from easy_quant.factors.reference import definitions
from easy_quant.factors.statistical import expected_return
from easy_quant.factors.technical import (
    moving_average,
    moving_average_convergence_divergence,
    relative_strength_index,
)
from easy_quant.factors.types import FactorDefinition
from easy_quant.platform_library.registry import FactorRegistry


def build_default_registry() -> FactorRegistry:
    registry = FactorRegistry()
    items = [
        (
            "technical.ma",
            "移动平均线（含 5 日均线）",
            "计算指定窗口的收盘价均线；window=5 即为 5 日均线",
            {"symbol": "证券代码", "window": "窗口"},
            "均线或数据不足",
            "factor('technical.ma', symbol='000001', window=5)",
            (
                "{'available': True, 'value': Decimal('10.50'), 'window': 5}"
                "\n数据不足：{'available': False, 'required': 5, 'actual': 3}"
            ),
            moving_average,
        ),
        (
            "stat.expected-return",
            "历史预期回报",
            "由可见历史收益估计胜率和预期回报",
            {"symbol": "证券代码"},
            "胜率与预期回报",
            "factor('stat.expected-return', symbol='000001')",
            (
                "{'available': True, 'expected_return': Decimal('0.012'), "
                "'win_rate': Decimal('0.6')}\n数据不足："
                "{'available': False, 'expected_return': None, 'win_rate': None}"
            ),
            expected_return,
        ),
        (
            "technical.rsi",
            "相对强弱指标 RSI",
            "根据截至决策时点可见的收盘价计算 RSI",
            {"symbol": "证券代码", "window": "窗口，默认 14"},
            "RSI 或数据不足说明",
            "factor('technical.rsi', symbol='000001', window=14)",
            (
                "{'available': True, 'value': Decimal('62.5'), 'window': 14}"
                "\n数据不足：{'available': False, 'required': 15, 'actual': 10}"
            ),
            relative_strength_index,
        ),
        (
            "technical.macd",
            "指数平滑异同移动平均线 MACD",
            "计算 DIF、DEA 与柱值，不依赖 TA-Lib",
            {"symbol": "证券代码", "fast": "快线", "slow": "慢线", "signal": "信号线"},
            "DIF、DEA、柱值或数据不足说明",
            "factor('technical.macd', symbol='000001', fast=12, slow=26, signal=9)",
            (
                "{'available': True, 'dif': Decimal('0.12'), 'dea': Decimal('0.08'), "
                "'histogram': Decimal('0.08')}\n数据不足："
                "{'available': False, 'required': 35, 'actual': 20}"
            ),
            moving_average_convergence_divergence,
        ),
    ]
    for item in items:
        defaults = {
            "technical.ma": {"window": 5},
            "technical.rsi": {"window": 14},
            "technical.macd": {"fast": 12, "slow": 26, "signal": 9},
        }.get(item[0], {})
        registry.register(
            FactorDefinition(
                *item,
                defaults=defaults,
                datasets=("daily-bars",),
                integer_parameters=tuple(defaults),
                history_parameter="window"
                if item[0] in {"technical.ma", "technical.rsi"}
                else None,
                history_extra=int(item[0] == "technical.rsi"),
            )
        )
    for definition in definitions():
        registry.register(definition)
    return registry

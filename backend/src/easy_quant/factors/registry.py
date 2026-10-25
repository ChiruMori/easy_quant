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
            (
                "计算逻辑：最近window个收盘价求算术均值，window="
                "5即5日均线。结果含义：描述近期平均价格水平，用于平滑价格；"
                "不直接规定买卖方向。"
            ),
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
            (
                "计算逻辑：相邻收盘价比减1得到日收益，求平均值作为expec"
                "ted_return；正收益日数除以收益样本数作为win_r"
                "ate。结果含义：二者只描述输入历史样本，不是未来收益或获胜"
                "概率保证。"
            ),
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
            (
                "计算逻辑：最近window个价差分别取上涨和下跌绝对值的简单"
                "均值，RS=平均上涨/平均下跌，RSI=100-100/(1"
                "+RS)；平均下跌为零时返回100。结果含义：较高表示近期上"
                "涨价差相对更强；全平也按当前实现返回100。此接口不是Wil"
                "der递归平滑的rsi。"
            ),
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
            (
                "计算逻辑：快慢EMA之差为DIF，DIF的信号EMA为DEA"
                "，柱值=2*(DIF-DEA)，EMA从窗口首值递推。结果含"
                "义：DIF正表示快线高于慢线，柱值正表示DIF高于DEA；数"
                "值使用价格单位，不代表收益率。"
            ),
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

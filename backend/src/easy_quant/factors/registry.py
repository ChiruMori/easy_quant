from __future__ import annotations

from easy_quant.domain.shared.errors import NotFoundError, ValidationError
from easy_quant.factors.context import FactorContext
from easy_quant.factors.market import daily_bars, latest_record, market_value, record_history
from easy_quant.factors.statistical import expected_return
from easy_quant.factors.technical import (
    moving_average,
    moving_average_convergence_divergence,
    relative_strength_index,
)
from easy_quant.factors.types import FactorDefinition


class FactorRegistry:
    def __init__(self) -> None:
        self._items: dict[str, FactorDefinition] = {}

    def register(self, definition: FactorDefinition) -> None:
        if definition.key in self._items:
            raise ValidationError("因子重复注册", {"key": definition.key})
        if not all((definition.description, definition.output, definition.example)):
            raise ValidationError("因子文档不完整", {"key": definition.key})
        self._items[definition.key] = definition

    def list(self) -> tuple[FactorDefinition, ...]:
        return tuple(self._items.values())

    def get(self, key: str) -> FactorDefinition:
        try:
            return self._items[key]
        except KeyError as error:
            raise NotFoundError("factor") from error

    def call(self, key: str, context: FactorContext, parameters: dict[str, object]) -> object:
        definition = self.get(key)
        missing = definition.parameters.keys() - parameters.keys()
        if missing:
            raise ValidationError("缺少因子参数", {"fields": sorted(missing)})
        return definition.function(context, parameters)


def build_default_registry() -> FactorRegistry:
    registry = FactorRegistry()
    items = [
        (
            "market.daily-bars",
            "K 线",
            "读取截至 as_of 可见的日线 K 线",
            {"symbol": "证券代码"},
            "K 线序列",
            "factor('market.daily-bars', symbol='000001')",
            daily_bars,
        ),
        (
            "market.value",
            "市值",
            "读取最新可见市值",
            {"symbol": "证券代码"},
            "市值记录",
            "factor('market.value', symbol='000001')",
            market_value,
        ),
        (
            "technical.ma",
            "移动平均线（含 5 日均线）",
            "计算指定窗口的收盘价均线；window=5 即为 5 日均线",
            {"symbol": "证券代码", "window": "窗口"},
            "均线或数据不足",
            "factor('technical.ma', symbol='000001', window=5)",
            moving_average,
        ),
        (
            "stat.expected-return",
            "历史预期回报",
            "由可见历史收益估计胜率和预期回报",
            {"symbol": "证券代码"},
            "胜率与预期回报",
            "factor('stat.expected-return', symbol='000001')",
            expected_return,
        ),
        (
            "technical.rsi",
            "相对强弱指标 RSI",
            "根据截至决策时点可见的收盘价计算 RSI",
            {"symbol": "证券代码", "window": "窗口，默认 14"},
            "RSI 或数据不足说明",
            "factor('technical.rsi', symbol='000001', window=14)",
            relative_strength_index,
        ),
        (
            "technical.macd",
            "指数平滑异同移动平均线 MACD",
            "计算 DIF、DEA 与柱值，不依赖 TA-Lib",
            {"symbol": "证券代码", "fast": "快线", "slow": "慢线", "signal": "信号线"},
            "DIF、DEA、柱值或数据不足说明",
            "factor('technical.macd', symbol='000001', fast=12, slow=26, signal=9)",
            moving_average_convergence_divergence,
        ),
        (
            "fundamental.latest",
            "最新基本面记录",
            "读取指定基本面数据集截至决策时点的最新记录",
            {"symbol": "证券代码", "dataset": "基本面数据集"},
            "最新记录或空值",
            "factor('fundamental.latest', symbol='000001', dataset='valuation-indicators')",
            latest_record,
        ),
        (
            "fundamental.history",
            "历史基本面记录",
            "按可获知时间读取财务、估值、质押等历史记录",
            {"symbol": "证券代码", "dataset": "基本面数据集"},
            "历史记录序列",
            "factor('fundamental.history', symbol='000001', dataset='financial-indicators')",
            record_history,
        ),
    ]
    for item in items:
        registry.register(FactorDefinition(*item))
    return registry

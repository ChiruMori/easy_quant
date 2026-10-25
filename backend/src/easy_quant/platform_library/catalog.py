from easy_quant.platform_library.market import (
    daily_bars,
    latest_record,
    market_value,
    record_history,
)
from easy_quant.platform_library.registry import FactorRegistry
from easy_quant.platform_library.types import FactorDefinition


def build_library_registry() -> FactorRegistry:
    registry = FactorRegistry()
    items = [
        (
            "market.daily-bars",
            "K 线",
            "读取截至 as_of 可见的日线 K 线",
            {"symbol": "证券代码"},
            "K 线序列",
            "library('market.daily-bars', symbol='000001')",
            (
                '[{"symbol": "000001", "trading_day": "2026-09-30", '
                '"close": "10.50", "volume": "100000"}]'
            ),
            daily_bars,
        ),
        (
            "market.value",
            "市值",
            "读取最新可见市值",
            {"symbol": "证券代码"},
            "市值记录",
            "library('market.value', symbol='000001')",
            (
                '{"symbol": "000001", "market_cap": 120000000000, '
                '"available_at": "2026-09-30T15:00:00+08:00"}\n无记录时：None'
            ),
            market_value,
        ),
        (
            "fundamental.latest",
            "最新基本面记录",
            "读取指定基本面数据集截至决策时点的最新记录",
            {"symbol": "证券代码", "dataset": "基本面数据集"},
            "最新记录或空值",
            "library('fundamental.latest', symbol='000001', dataset='valuation-indicators')",
            (
                '{"symbol": "000001", "available_at": "2026-09-30T15:00:00+08:00", '
                '"pb_ratio": 1.2}\n无记录时：None'
            ),
            latest_record,
        ),
        (
            "fundamental.history",
            "历史基本面记录",
            "按可获知时间读取财务、估值、质押等历史记录",
            {"symbol": "证券代码", "dataset": "基本面数据集"},
            "历史记录序列",
            "library('fundamental.history', symbol='000001', dataset='financial-indicators')",
            (
                '[{"symbol": "000001", "available_at": "2026-04-30T15:00:00+08:00"}, '
                '{"symbol": "000001", "available_at": "2026-08-31T15:00:00+08:00"}]'
                "\n无记录时：[]"
            ),
            record_history,
        ),
    ]
    for item in items:
        registry.register(FactorDefinition(*item))
    return registry

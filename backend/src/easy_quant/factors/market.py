"""兼容导入；数据能力定义位于 platform_library。"""

from easy_quant.platform_library.market import (
    daily_bars,
    latest_record,
    market_value,
    record_history,
)

__all__ = ["daily_bars", "latest_record", "market_value", "record_history"]

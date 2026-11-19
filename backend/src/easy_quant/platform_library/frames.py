"""存储数字字符串/Decimal 到 float64 的显式研究边界。"""

from collections.abc import Iterable, Mapping
from typing import Any, cast

import pandas as pd

NUMERIC_FIELDS = {
    "adjusted_volume",
    "adjusted_vwap",
    "raw_open",
    "raw_high",
    "raw_low",
    "raw_close",
    "price_scale",
    "share_scale",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "pe_ratio",
    "pb_ratio",
    "market_cap",
    "circulating_market_cap",
    "roe",
    "net_profit",
    "adjusted_net_profit",
    "pledge_ratio",
}


def research_frame(rows: Iterable[Mapping[str, object]], extra_fields=()):
    records = list(rows)
    names = dict.fromkeys(name for row in records for name in row)
    numeric = NUMERIC_FIELDS | set(extra_fields)
    # 按列一次构建，避免每只股票逐列插入/转换 Series 的开销。
    # 非法字符串仍报错；缺失保持 NaN，计算者决定完整性。
    columns = {}
    for name in names:
        values = [row.get(name) for row in records]
        columns[name] = (
            cast(Any, pd.to_numeric(values, errors="raise")).astype("float64")
            if name in numeric
            else values
        )
    frame = pd.DataFrame(columns)
    if "trading_day" in frame:
        frame = frame.sort_values("trading_day", kind="stable").reset_index(drop=True)
    return frame

"""存储数字字符串/Decimal 到 float64 的显式研究边界。"""

from collections.abc import Iterable, Mapping
from typing import Any, cast

import pandas as pd

NUMERIC_FIELDS = {
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
    frame = pd.DataFrame([dict(row) for row in rows])
    for name in (NUMERIC_FIELDS | set(extra_fields)) & set(frame.columns):
        # 非法字符串不能静默进入研究集；缺失保持 NaN，计算者决定完整性。
        frame[name] = cast(Any, pd.to_numeric(frame[name], errors="raise")).astype("float64")
    if "trading_day" in frame:
        frame = frame.sort_values("trading_day", kind="stable").reset_index(drop=True)
    return frame

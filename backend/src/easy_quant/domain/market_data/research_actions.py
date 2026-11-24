"""通达信价格调整契约；不包含或推测现金/股份到账规则。"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from easy_quant.domain.market_data.corporate_actions import day, number

TDX_PRICE_DATASET = "tdx-price-adjustments"
TDX_PRICE_VERSION = "tdx-price-v1"


@dataclass(frozen=True)
class PriceAdjustment:
    event_id: str
    symbol: str
    ex_date: date
    previous_close: Decimal
    price_ratio: Decimal
    share_multiplier: Decimal
    cash_per_share: Decimal
    rights_ratio: Decimal
    rights_price: Decimal
    record_key: str

    @classmethod
    def parse(cls, row):
        result = cls(
            str(row["event_id"]),
            str(row["symbol"]),
            day(row["ex_date"]),
            number(row["previous_close"]),
            number(row["price_ratio"]),
            number(row["share_multiplier"]),
            number(row["cash_per_share"]),
            number(row["rights_ratio"]),
            number(row["rights_price"]),
            str(row["record_key"]),
        )
        if min(result.previous_close, result.price_ratio, result.share_multiplier) <= 0:
            raise ValueError("价格调整基准、比例必须为正")
        if min(result.cash_per_share, result.rights_ratio, result.rights_price) < 0:
            raise ValueError("价格调整分量不得为负")
        return result

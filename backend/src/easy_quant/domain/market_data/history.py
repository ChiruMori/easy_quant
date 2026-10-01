from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from easy_quant.domain.shared.errors import ValidationError


@dataclass(frozen=True, slots=True)
class HistoryBar:
    symbol: str
    trading_day: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    amount: Decimal
    available_at: datetime

    def validate(self) -> None:
        values = (self.open, self.high, self.low, self.close, self.volume, self.amount)
        if not all(value.is_finite() for value in values):
            raise ValidationError("日线包含非有限数值")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValidationError("日线价格必须大于零")
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValidationError("日线最高/最低价与开收盘价不一致")
        if self.volume < 0 or self.amount < 0:
            raise ValidationError("成交量和成交额不得为负")
        if self.available_at.tzinfo is None:
            raise ValidationError("日线可获知时间必须包含时区")

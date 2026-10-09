from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class BacktestCreateRequest(BaseModel):
    strategy_version_id: str
    symbols: list[str] = Field(default_factory=list)
    start_day: date
    end_day: date
    initial_cash: Decimal = Field(gt=0)
    fee_rate: Decimal = Field(default=Decimal("0.0003"), ge=0)
    slippage_rate: Decimal = Field(default=Decimal("0.0001"), ge=0)
    benchmark: str | None = None
    random_seed: int = 0
    parameters: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def dates_are_ordered(self):
        if self.start_day > self.end_day:
            raise ValueError("开始日期不得晚于结束日期")
        return self


class BacktestCompareRequest(BaseModel):
    run_ids: list[str] = Field(min_length=2, max_length=2)

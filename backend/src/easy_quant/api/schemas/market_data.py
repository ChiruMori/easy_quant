from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from easy_quant.domain.market_data.indices import benchmark_symbol, is_index


class AcquisitionRequest(BaseModel):
    dataset_key: str = Field(min_length=1, max_length=80)
    parameters: dict[str, object] = Field(default_factory=dict)
    symbols: list[str] = Field(default_factory=list)
    start_day: str | None = None
    end_day: str | None = None
    force: bool = False


class SourceOrderRequest(BaseModel):
    source_keys: list[str] = Field(min_length=1)
    enabled_keys: list[str] = Field(default_factory=list)


class InstrumentStatusRequest(BaseModel):
    status: Literal["active", "suspended"]
    reason: str = Field(min_length=4, max_length=500)


class IndexSyncRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=50)
    start_day: date
    end_day: date

    @field_validator("symbols")
    @classmethod
    def indices_only(cls, values: list[str]) -> list[str]:
        normalized = sorted({benchmark_symbol(value) for value in values})
        if any(not is_index(symbol) for symbol in normalized):
            raise ValueError("请选择指数代码，股票不能通过此入口同步")
        return normalized

    @model_validator(mode="after")
    def dates_are_ordered(self):
        if self.start_day > self.end_day:
            raise ValueError("开始日期不得晚于结束日期")
        return self

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class StrategyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = ""
    source_code: str = Field(min_length=1, max_length=100_000)


class StrategyRunRequest(BaseModel):
    trading_day: date
    parameters: dict[str, object] = Field(default_factory=dict)
    allow_mock: bool = False
    initial_cash: Decimal = Field(default=Decimal("1000000"), gt=0, allow_inf_nan=False)

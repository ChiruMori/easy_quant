from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class StrategyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = ""
    source_code: str = Field(min_length=1, max_length=100_000)

    @field_validator("name")
    @classmethod
    def non_blank_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("策略名称不能为空")
        return value.strip()


class StrategyRunRequest(BaseModel):
    trading_day: date
    parameters: dict[str, object] = Field(default_factory=dict)
    allow_mock: bool = False
    initial_cash: Decimal = Field(default=Decimal("1000000"), gt=0, allow_inf_nan=False)
    source_code: str | None = Field(default=None, min_length=1, max_length=100_000)
    strategy_id: str | None = None
    strategy_version_id: str | None = None


class DraftUpdateRequest(StrategyCreateRequest):
    expected_revision: int = Field(ge=0, strict=True)

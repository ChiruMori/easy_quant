from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class ManualOperationRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=80)
    symbol: str = Field(min_length=1, max_length=32)
    action: Literal["buy", "sell"]
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(gt=0)
    fee: Decimal = Field(default=Decimal(0), ge=0)
    risk_acknowledged: bool = False
    confirmed_increase: Decimal = Field(default=Decimal(0), ge=0)


class StartLiveRequest(BaseModel):
    backtest_id: str
    strategy_version_id: str | None = None
    name: str = Field(min_length=1, max_length=160, pattern=r"\S")
    initial_cash: Decimal = Field(gt=0, allow_inf_nan=False)
    parameters: dict[str, object] = Field(default_factory=dict)
    positions: dict[str, Decimal] = Field(default_factory=dict)
    subscription_ids: list[str] = Field(min_length=1)
    after_market_enabled: bool = False

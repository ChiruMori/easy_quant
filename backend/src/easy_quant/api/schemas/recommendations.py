from decimal import Decimal

from pydantic import BaseModel, Field


class RecommendationActionRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=80)
    expected_version: int = Field(ge=0)
    symbol: str | None = None
    action: str | None = None
    quantity: Decimal = Field(default=Decimal(0), ge=0)
    price: Decimal = Field(default=Decimal(0), ge=0)
    fee: Decimal = Field(default=Decimal(0), ge=0)

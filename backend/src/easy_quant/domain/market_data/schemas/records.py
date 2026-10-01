from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")
    available_at: datetime


class Security(Record):
    symbol: str
    name: str
    exchange: str


class DailyBar(Record):
    symbol: str
    trading_day: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class CompanyProfile(Record):
    symbol: str
    industry: str | None = None
    description: str | None = None


class Shareholder(Record):
    symbol: str
    report_day: date
    shareholder_name: str
    holding_ratio: Decimal | None = None


class ConceptMembership(Record):
    symbol: str
    concept: str


class MarketValue(Record):
    symbol: str
    trading_day: date
    total: Decimal
    circulating: Decimal | None = None

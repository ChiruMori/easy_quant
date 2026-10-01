from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from easy_quant.infrastructure.persistence.base import Base, UtcDateTime


class ActualOperationModel(Base):
    __tablename__ = "actual_operations"
    __table_args__ = (
        UniqueConstraint("idempotency_key"),
        Index("ix_operations_owner_time", "owner_id", "occurred_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    recommendation_id: Mapped[str] = mapped_column(ForeignKey("recommendations.id"), nullable=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(80), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)


class PortfolioLedgerEntryModel(Base):
    __tablename__ = "portfolio_ledger_entries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    live_instance_id: Mapped[str] = mapped_column(ForeignKey("live_instances.id"), nullable=False)
    operation_id: Mapped[str] = mapped_column(
        ForeignKey("actual_operations.id"), unique=True, nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    cash_delta: Mapped[Decimal] = mapped_column(Numeric(28, 8), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(20))
    quantity_delta: Mapped[Decimal] = mapped_column(Numeric(28, 8), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)

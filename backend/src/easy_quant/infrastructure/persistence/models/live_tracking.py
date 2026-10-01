from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from easy_quant.infrastructure.persistence.base import Base, UtcDateTime


class LiveInstanceModel(Base):
    __tablename__ = "live_instances"
    __table_args__ = (Index("ix_live_owner_status", "owner_id", "status"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    backtest_id: Mapped[str] = mapped_column(String(36), nullable=False)
    strategy_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    next_decision_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    parameters_json: Mapped[str] = mapped_column(Text, nullable=False)


class RecommendationModel(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        UniqueConstraint("business_key"),
        Index("ix_recommendations_owner_decision", "owner_id", "decision_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    live_instance_id: Mapped[str] = mapped_column(ForeignKey("live_instances.id"), nullable=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    business_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    decision_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

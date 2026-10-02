from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from easy_quant.infrastructure.persistence.base import Base, UtcDateTime


class StrategyModel(Base):
    __tablename__ = "strategies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    current_version_id: Mapped[str | None] = mapped_column(String(36))


class StrategyVersionModel(Base):
    __tablename__ = "strategy_versions"
    __table_args__ = (UniqueConstraint("strategy_id", "number"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    strategy_id: Mapped[str] = mapped_column(ForeignKey("strategies.id"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_code: Mapped[str] = mapped_column(
        Text().with_variant(LONGTEXT(), "mysql"), nullable=False
    )
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_version_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)

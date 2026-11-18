"""阶段级幂等回执与原子累加；不与业务实体建立外键。"""

from sqlalchemy import BigInteger, String, select
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.orm import Mapped, mapped_column

from easy_quant.infrastructure.persistence.base import Base


class FactorStatisticsModel(Base):
    __tablename__ = "factor_statistics"
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    calls: Mapped[int] = mapped_column(BigInteger, nullable=False)
    elapsed_ns: Mapped[int] = mapped_column(BigInteger, nullable=False)


class FactorReceiptModel(Base):
    __tablename__ = "factor_statistic_receipts"
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)


class InMemoryFactorStatistics:
    def __init__(self):
        self.events = set()
        self.totals = {}

    def record(self, event_id, metrics):
        if event_id in self.events or not metrics:
            return
        self.events.add(event_id)
        for key, value in metrics.items():
            total = self.totals.setdefault(key, {"calls": 0, "elapsed_ns": 0})
            total["calls"] += value["calls"]
            total["elapsed_ns"] += value["elapsed_ns"]

    def snapshot(self):
        return {key: dict(value) for key, value in self.totals.items()}


class SqlFactorStatistics:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def record(self, event_id, metrics):
        if not metrics:
            return
        with self.session_factory.begin() as session:
            receipt = session.execute(
                insert(FactorReceiptModel).values(event_id=event_id).prefix_with("IGNORE")
            )
            if receipt.rowcount == 0:
                return
            for key, value in sorted(metrics.items()):
                statement = insert(FactorStatisticsModel).values(key=key, **value)
                session.execute(
                    statement.on_duplicate_key_update(
                        calls=FactorStatisticsModel.calls + statement.inserted.calls,
                        elapsed_ns=FactorStatisticsModel.elapsed_ns + statement.inserted.elapsed_ns,
                    )
                )

    def snapshot(self):
        with self.session_factory() as session:
            return {
                row.key: {"calls": row.calls, "elapsed_ns": row.elapsed_ns}
                for row in session.scalars(select(FactorStatisticsModel))
            }

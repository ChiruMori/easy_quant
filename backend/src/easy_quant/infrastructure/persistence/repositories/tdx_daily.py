from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date, datetime
from typing import cast

from sqlalchemy import Table, func, select, text
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from easy_quant.application.services.tdx_incremental import DailyArchive, DayCheckpoint
from easy_quant.infrastructure.persistence.models.market_data_records import (
    DailyBarModel,
    HistoryImportStockModel,
    InstrumentModel,
    TdxDailyCheckpointModel,
    TradingDayModel,
)
from easy_quant.infrastructure.persistence.repositories.history_import import (
    bar_values,
    bars_upsert,
)

_LOCK = "CONCAT('easy_quant_tdx_', LEFT(SHA2(DATABASE(), 256), 40))"


class SqlDailyStore:
    def __init__(self, factory: sessionmaker[Session], now: Callable[[], datetime]) -> None:
        self.factory, self.now = factory, now
        self._lock_session: Session | None = None

    @contextmanager
    def exclusive(self) -> Iterator[None]:
        try:
            with self.factory() as session:
                if session.scalar(text(f"SELECT GET_LOCK({_LOCK}, 0)")) != 1:
                    raise RuntimeError("另一个通达信更新任务正在执行，请稍后重试")
                self._lock_session = session
                try:
                    yield
                finally:
                    self._lock_session = None
                    session.execute(text(f"SELECT RELEASE_LOCK({_LOCK})"))
        except SQLAlchemyError as error:
            raise RuntimeError(f"数据库不可用（{type(error).__name__}）") from None

    def baseline(self) -> date | None:
        with self.factory() as session:
            return session.scalar(select(func.max(HistoryImportStockModel.last_day)))

    def checkpoints(self) -> dict[date, DayCheckpoint]:
        with self.factory() as session:
            return {
                row.trading_day: DayCheckpoint(row.status, row.archive_sha256)
                for row in session.scalars(select(TdxDailyCheckpointModel))
            }

    def write_day(self, archive: DailyArchive) -> None:
        try:
            self._ensure_lock()
            with self.factory.begin() as session:
                symbols = [bar.symbol for bar in archive.bars]
                # 全量股票检查点与整只股票的不复权历史同事务写入；已有写入口
                # 均禁止切换口径。利用该凭据，避免每日再次扫描千万行历史。
                imported = set(session.scalars(select(HistoryImportStockModel.symbol).distinct()))
                unchecked = set(symbols) - imported
                conflict = (
                    session.scalar(
                        select(DailyBarModel.symbol)
                        .where(
                            DailyBarModel.symbol.in_(unchecked), DailyBarModel.adjustment != "none"
                        )
                        .limit(1)
                    )
                    if unchecked
                    else None
                )
                if conflict is not None:
                    raise ValueError("已有日线口径非不复权，拒绝混入增量行情")
                values = [bar_values(bar, archive.sha256) for bar in archive.bars]
                for offset in range(0, len(values), 2000):
                    session.execute(bars_upsert(), values[offset : offset + 2000])
                instruments = []
                for symbol in symbols:
                    exchange = (
                        "上海证券交易所"
                        if symbol.startswith("6")
                        else "北京证券交易所"
                        if symbol.startswith(("4", "8", "92"))
                        else "深圳证券交易所"
                    )
                    instruments.append(
                        dict(symbol=symbol, name="", status="unknown", exchange=exchange)
                    )
                statement = insert(cast(Table, InstrumentModel.__table__))
                session.execute(
                    statement.on_duplicate_key_update(symbol=statement.inserted.symbol), instruments
                )
                calendar = insert(cast(Table, TradingDayModel.__table__))
                session.execute(
                    calendar.on_duplicate_key_update(trading_day=calendar.inserted.trading_day),
                    [{"trading_day": archive.day}],
                )
                self._save_checkpoint(
                    session, archive.day, "succeeded", "", archive.sha256, len(values)
                )
        except SQLAlchemyError as error:
            raise RuntimeError(f"单日事务失败（{type(error).__name__}），可重跑恢复") from None

    def mark(self, day: date, status: str, reason: str, digest: str | None = None) -> None:
        try:
            self._ensure_lock()
            with self.factory.begin() as session:
                prior = session.get(TdxDailyCheckpointModel, day)
                if prior is not None and prior.status == "succeeded" and status != "failed":
                    return
                self._save_checkpoint(
                    session,
                    day,
                    status,
                    reason[:200],
                    prior.archive_sha256 if prior and status == "failed" else digest,
                    prior.row_count if prior and status == "failed" else 0,
                )
        except SQLAlchemyError as error:
            raise RuntimeError(f"日期检查点保存失败（{type(error).__name__}）") from None

    def _ensure_lock(self) -> None:
        if (
            self._lock_session is not None
            and self._lock_session.scalar(text(f"SELECT IS_USED_LOCK({_LOCK}) = CONNECTION_ID()"))
            != 1
        ):
            raise RuntimeError("通达信更新数据库锁已丢失，请重跑恢复")

    def _save_checkpoint(
        self, session: Session, day: date, status: str, reason: str, digest: str | None, rows: int
    ) -> None:
        checkpoint = insert(cast(Table, TdxDailyCheckpointModel.__table__))
        session.execute(
            checkpoint.on_duplicate_key_update(
                **{
                    name: checkpoint.inserted[name]
                    for name in ("status", "reason", "archive_sha256", "row_count", "checked_at")
                }
            ),
            [
                {
                    "trading_day": day,
                    "status": status,
                    "reason": reason,
                    "archive_sha256": digest,
                    "row_count": rows,
                    "checked_at": self.now(),
                }
            ],
        )

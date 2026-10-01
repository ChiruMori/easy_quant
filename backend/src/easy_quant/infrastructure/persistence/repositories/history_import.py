from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from typing import Any, cast

from sqlalchemy import Table, select
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from easy_quant.domain.market_data.history import HistoryBar
from easy_quant.infrastructure.persistence.models.market_data_records import (
    DailyBarModel,
    HistoryImportStockModel,
    InstrumentModel,
    TradingDayModel,
)


def bar_values(bar: HistoryBar, archive_sha256: str) -> dict[str, Any]:
    return {
        "symbol": bar.symbol,
        "trading_day": bar.trading_day,
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
        "amount": bar.amount,
        "available_at": bar.available_at,
        "source": "tdx-official",
        "adjustment": "none",
        "archive_sha256": archive_sha256,
    }


def bars_upsert():
    statement = insert(cast(Table, DailyBarModel.__table__))
    return statement.on_duplicate_key_update(
        **{
            column.name: statement.inserted[column.name]
            for column in DailyBarModel.__table__.columns
            if column.name not in {"symbol", "trading_day"}
        }
    )


class SqlHistoryStore:
    def __init__(
        self,
        factory: sessionmaker[Session],
        now: Callable[[], datetime],
        bulk_loader: Callable[[Session, list[HistoryBar], str], None] | None = None,
    ) -> None:
        self.factory, self.now = factory, now
        self._completed: dict[str, set[str]] = {}
        self._known_days: set[date] | None = None
        self.bulk_loader = bulk_loader

    def completed(self, archive_sha256: str, symbol: str) -> bool:
        if archive_sha256 not in self._completed:
            with self.factory() as session:
                self._completed[archive_sha256] = set(
                    session.scalars(
                        select(HistoryImportStockModel.symbol).where(
                            HistoryImportStockModel.archive_sha256 == archive_sha256
                        )
                    )
                )
        return symbol in self._completed[archive_sha256]

    def write_stocks(
        self, archive_sha256: str, stocks: list[tuple[str, list[HistoryBar]]], batch_size: int
    ) -> None:
        try:
            symbols = [symbol for symbol, _bars in stocks]
            with self.factory.begin() as session:
                if self._known_days is None:
                    self._known_days = set(session.scalars(select(TradingDayModel.trading_day)))
                conflict = session.scalar(
                    select(DailyBarModel.symbol)
                    .where(DailyBarModel.symbol.in_(symbols), DailyBarModel.adjustment != "none")
                    .limit(1)
                )
                if conflict is not None:
                    raise ValueError("已有日线口径非不复权，拒绝覆盖该股票")
                bars = [bar for _symbol, stock_bars in stocks for bar in stock_bars]
                if self.bulk_loader is not None:
                    self.bulk_loader(session, bars, archive_sha256)
                else:
                    for offset in range(0, len(bars), batch_size):
                        batch = bars[offset : offset + batch_size]
                        session.execute(
                            bars_upsert(), [bar_values(bar, archive_sha256) for bar in batch]
                        )
                new_days = {bar.trading_day for bar in bars} - self._known_days
                if new_days:
                    days = insert(cast(Table, TradingDayModel.__table__))
                    session.execute(
                        days.on_duplicate_key_update(trading_day=days.inserted.trading_day),
                        [{"trading_day": day} for day in sorted(new_days)],
                    )
                instruments = []
                checkpoints = []
                for symbol, stock_bars in stocks:
                    exchange = (
                        "上海证券交易所"
                        if symbol.startswith("6")
                        else "北京证券交易所"
                        if symbol.startswith(("4", "8", "92"))
                        else "深圳证券交易所"
                    )
                    instruments.append(
                        dict(symbol=symbol, name="", exchange=exchange, status="unknown")
                    )
                    checkpoints.append(
                        dict(
                            archive_sha256=archive_sha256,
                            symbol=symbol,
                            row_count=len(stock_bars),
                            first_day=stock_bars[0].trading_day,
                            last_day=stock_bars[-1].trading_day,
                            completed_at=self.now(),
                        )
                    )
                instrument = insert(cast(Table, InstrumentModel.__table__))
                session.execute(
                    instrument.on_duplicate_key_update(symbol=instrument.inserted.symbol),
                    instruments,
                )
                checkpoint = insert(cast(Table, HistoryImportStockModel.__table__))
                session.execute(
                    checkpoint.on_duplicate_key_update(
                        row_count=checkpoint.inserted.row_count,
                        first_day=checkpoint.inserted.first_day,
                        last_day=checkpoint.inserted.last_day,
                        completed_at=checkpoint.inserted.completed_at,
                    ),
                    checkpoints,
                )
            self._completed.setdefault(archive_sha256, set()).update(symbols)
            self._known_days.update(new_days)
        except SQLAlchemyError as error:
            # DBAPI 异常可能含连接信息和 SQL 参数，不输出到终端或报告。
            raise RuntimeError(f"数据库批次失败（{type(error).__name__}），可重跑恢复") from None

from __future__ import annotations

import gzip
import json
import zlib
from bisect import bisect_left, bisect_right
from calendar import monthrange
from collections.abc import Callable, Iterable, Iterator
from contextlib import nullcontext
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import Table, case, delete, func, or_, select, tuple_
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.orm import Session

from easy_quant.domain.scheduling.entities import Job
from easy_quant.domain.shared.errors import StateConflictError
from easy_quant.infrastructure.persistence.bar_storage import BAR_STORAGE
from easy_quant.infrastructure.persistence.models.backtesting import (
    BacktestMetricModel,
    BacktestPeriodModel,
    BacktestRunModel,
    DataSnapshotChunkModel,
    DataSnapshotModel,
    SimulatedTradeModel,
)
from easy_quant.infrastructure.persistence.models.market_data_records import (
    DailyBarModel,
    InstrumentModel,
    JsonMarketRecordModel,
    TradingDayModel,
)
from easy_quant.infrastructure.persistence.repositories.jobs import SqlAlchemyJobRepository
from easy_quant.infrastructure.persistence.snapshot_spool import SnapshotSpool


def bar_coverage_statement(*, include_count: bool = True, Bar: Any = DailyBarModel) -> Any:
    # MariaDB 在大库中可能仍选择较宽的聚簇主键；明确读取股票/日期二级索引。
    fields = [
        Bar.symbol,
        func.min(Bar.trading_day),
        func.max(Bar.trading_day),
    ]
    if include_count:
        fields.append(func.count())
    return (
        select(*fields)
        .with_hint(Bar, "FORCE INDEX (ix_daily_bars_coverage)", dialect_name="mysql")
        .group_by(Bar.symbol)
    )


def _single_bar_adjustment(symbol: str, adjustments: set[str]) -> str | None:
    if len(adjustments) > 1:
        raise StateConflictError(
            "同一股票已有多种日线复权口径，无法自动补齐",
            {"symbol": symbol, "adjustments": sorted(adjustments)},
        )
    return next(iter(adjustments), None)


RUNTIME_SYMBOL_BATCH = 500


def runtime_symbols_statement(start_day: date, end_day: date, Bar: Any = DailyBarModel):
    return (
        select(Bar.symbol)
        .with_hint(Bar, "FORCE INDEX (ix_daily_bars_day_symbol)", dialect_name="mysql")
        .where(Bar.trading_day >= start_day, Bar.trading_day <= end_day)
        .distinct()
        .order_by(Bar.symbol)
    )


def runtime_batch_statement(
    symbols: list[str], start_day: date, end_day: date, Bar: Any = DailyBarModel
):
    return (
        select(
            Bar.symbol,
            Bar.trading_day,
            Bar.available_at,
            Bar.open,
            Bar.high,
            Bar.low,
            Bar.close,
        )
        .with_hint(Bar, "FORCE INDEX (PRIMARY)", dialect_name="mysql")
        .where(
            Bar.symbol.in_(symbols),
            Bar.trading_day >= start_day,
            Bar.trading_day <= end_day,
        )
        .order_by(Bar.symbol, Bar.trading_day)
    )


def snapshot_chunks(payload: bytes) -> list[bytes]:
    compressed = gzip.compress(payload, mtime=0)
    return [compressed[offset : offset + 60_000] for offset in range(0, len(compressed), 60_000)]


def streamed_snapshot_chunks(payload: SnapshotSpool) -> Iterator[bytes]:
    compressor = zlib.compressobj(wbits=31)
    buffer = bytearray()
    for block in payload.chunks():
        buffer.extend(compressor.compress(block))
        while len(buffer) >= 60_000:
            yield bytes(buffer[:60_000])
            del buffer[:60_000]
    buffer.extend(compressor.flush())
    while buffer:
        yield bytes(buffer[:60_000])
        del buffer[:60_000]


class InMemoryMarketDataStore:
    def __init__(
        self,
        daily_bars: dict[tuple[str, str], dict[str, Any]],
        instruments: dict[str, dict[str, Any]],
        trading_days: set[str],
        market_records: dict[tuple[str, str], dict[str, Any]] | None = None,
    ) -> None:
        self.daily_bars = daily_bars
        self.instruments = instruments
        self.trading_days = trading_days
        self.market_records = market_records if market_records is not None else {}

    def upsert_bars(self, rows: list[dict[str, Any]]) -> int:
        incoming = {str(row["symbol"]): str(row.get("adjustment", "unknown")) for row in rows}
        for existing in self.daily_bars.values():
            symbol = str(existing["symbol"])
            if symbol in incoming and existing.get("adjustment", "unknown") != incoming[symbol]:
                raise StateConflictError("日线复权口径冲突，拒绝混合写入", {"symbol": symbol})
        overwritten = 0
        for row in rows:
            key = (str(row["symbol"]), str(row["trading_day"]))
            overwritten += int(key in self.daily_bars)
            self.daily_bars[key] = row
            self.trading_days.add(str(row["trading_day"]))
        return overwritten

    def bar_coverage(self, symbols: list[str] | None = None) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        wanted = set(symbols) if symbols is not None else None
        for row in self.daily_bars.values():
            symbol = str(row["symbol"])
            if wanted is not None and symbol not in wanted:
                continue
            day = date.fromisoformat(str(row["trading_day"]))
            item = result.setdefault(symbol, {"first_day": day, "last_day": day, "count": 0})
            item["first_day"] = min(item["first_day"], day)
            item["last_day"] = max(item["last_day"], day)
            item["count"] += 1
        return result

    def bar_bounds(self) -> dict[str, dict[str, Any]]:
        return self.bar_coverage()

    def bar_adjustment(self, symbol: str) -> str | None:
        return _single_bar_adjustment(
            symbol,
            {
                str(row.get("adjustment", "unknown"))
                for row in self.daily_bars.values()
                if str(row["symbol"]) == symbol
            },
        )

    def upsert_instruments(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            symbol = str(row["symbol"])
            if (
                self.instruments.get(symbol, {}).get("status") == "suspended"
                and row.get("status", "active") == "active"
            ):
                row = {**row, "status": "suspended"}
            self.instruments[symbol] = row

    def set_instrument_status(self, symbol: str, status: str) -> bool:
        if symbol not in self.instruments:
            return False
        self.instruments[symbol]["status"] = status
        return True

    def set_instrument_statuses(self, symbols: list[str], status: str) -> None:
        for symbol in symbols:
            self.set_instrument_status(symbol, status)

    def mark_missing_instruments_delisted(self, active_symbols: set[str]) -> None:
        for symbol, instrument in self.instruments.items():
            if symbol not in active_symbols and not (
                symbol.startswith(("sh", "sz")) and len(symbol) == 8
            ):
                instrument["status"] = "delisted"

    def list_bars(
        self,
        start_day: date | None = None,
        end_day: date | None = None,
        symbol: str | None = None,
    ):
        return [
            row
            for row in self.daily_bars.values()
            if (start_day is None or date.fromisoformat(str(row["trading_day"])) >= start_day)
            and (end_day is None or date.fromisoformat(str(row["trading_day"])) <= end_day)
            and (symbol is None or str(row["symbol"]) == symbol)
        ]

    def list_runtime_bars(self, start_day: date, end_day: date) -> list[dict[str, Any]]:
        fields = ("symbol", "trading_day", "available_at", "open", "high", "low", "close")
        return [
            {field: row[field] for field in fields} for row in self.list_bars(start_day, end_day)
        ]

    def iter_runtime_bars(self, start_day: date, end_day: date) -> Iterator[dict[str, Any]]:
        yield from sorted(
            self.list_runtime_bars(start_day, end_day),
            key=lambda row: (str(row["trading_day"]), str(row["symbol"])),
        )

    def iter_snapshot_bars(self, start_day: date, end_day: date) -> Iterator[dict[str, Any]]:
        yield from sorted(
            self.list_bars(start_day, end_day),
            key=lambda row: (str(row["symbol"]), str(row["trading_day"])),
        )

    def list_instruments(self):
        return list(self.instruments.values())

    def get_instrument(self, symbol: str):
        return self.instruments.get(symbol)

    def coverage_page(
        self,
        *,
        page: int,
        page_size: int,
        search: str = "",
        status: str = "",
        after_symbol: str = "",
        before_symbol: str = "",
        target_day: date | None = None,
    ):
        coverage = self.bar_coverage()
        symbols = sorted(set(self.instruments) | set(coverage))
        if search:
            needle = search.casefold()
            symbols = [
                symbol
                for symbol in symbols
                if needle in symbol.casefold()
                or needle in str(self.instruments.get(symbol, {}).get("name", "")).casefold()
            ]

        def sync_status(summary):
            if not summary:
                return "未同步"
            if target_day and summary["last_day"] < target_day:
                return "数据落后"
            days = (summary["last_day"] - summary["first_day"]).days
            return "完全同步" if days >= 3652 else "部分同步" if days >= 1095 else "数据不足"

        if status:
            symbols = [
                symbol
                for symbol in symbols
                if (
                    "已退市"
                    if self.instruments.get(symbol, {}).get("status") == "delisted"
                    else "已停牌"
                    if self.instruments.get(symbol, {}).get("status") == "suspended"
                    else sync_status(coverage.get(symbol))
                )
                == status
            ]
        total = len(symbols)
        page = min(page, max(1, (total + page_size - 1) // page_size))
        if after_symbol:
            selected = [symbol for symbol in symbols if symbol > after_symbol][:page_size]
        elif before_symbol:
            selected = [symbol for symbol in symbols if symbol < before_symbol][-page_size:]
        else:
            selected = symbols[(page - 1) * page_size : page * page_size]
        return (
            len(set(self.instruments) | set(coverage)),
            total,
            page,
            [
                {**self.instruments.get(symbol, {"symbol": symbol}), **coverage.get(symbol, {})}
                for symbol in selected
            ],
        )

    def list_trading_days(self) -> set[date]:
        return {date.fromisoformat(item) for item in self.trading_days}

    def upsert_trading_days(self, days: list[date]) -> None:
        self.trading_days.update(day.isoformat() for day in days)

    def upsert_records(self, dataset_key: str, rows: list[dict[str, Any]]) -> int:
        overwritten = 0
        for row in rows:
            key = str(row["record_key"])
            overwritten += int((dataset_key, key) in self.market_records)
            self.market_records[(dataset_key, key)] = row
        return overwritten

    def list_records(self, dataset_key: str, symbol: str | None = None):
        return [
            row
            for (dataset, _), row in self.market_records.items()
            if dataset == dataset_key and (symbol is None or row.get("symbol") == symbol)
        ]


class SqlAlchemyMarketDataStore:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.storage = BAR_STORAGE

    def upsert_bars(self, rows: list[dict[str, Any]]) -> int:
        Bar = self.storage.logical
        PhysicalBar = self.storage.physical
        incoming = {str(row["symbol"]): str(row.get("adjustment", "unknown")) for row in rows}
        for row in rows:
            symbol = str(row["symbol"])
            if str(row.get("adjustment", "unknown")) != incoming[symbol]:
                raise StateConflictError("批次内复权口径冲突，拒绝混合写入", {"symbol": symbol})
        if incoming:
            existing = self.session.execute(
                select(Bar.symbol, Bar.adjustment).where(Bar.symbol.in_(incoming)).distinct()
            )
            for symbol, adjustment in existing:
                if adjustment != incoming[symbol]:
                    raise StateConflictError("日线复权口径冲突，拒绝混合写入", {"symbol": symbol})
        overwritten = 0
        values = []
        seen: set[tuple[str, date]] = set()
        for item in rows:
            symbol, day = str(item["symbol"]), date.fromisoformat(str(item["trading_day"]))
            overwritten += int((symbol, day) in seen)
            seen.add((symbol, day))
            values.append(
                dict(
                    symbol=symbol,
                    trading_day=day,
                    open=Decimal(str(item["open"])),
                    high=Decimal(str(item["high"])),
                    low=Decimal(str(item["low"])),
                    close=Decimal(str(item["close"])),
                    volume=Decimal(str(item["volume"])),
                    available_at=datetime.fromisoformat(str(item["available_at"])),
                    source=str(item.get("source", "unknown")),
                    adjustment=str(item.get("adjustment", "unknown")),
                    amount=Decimal(str(item["amount"])) if item.get("amount") is not None else None,
                    archive_sha256=item.get("archive_sha256"),
                )
            )
        keys = sorted(seen)
        for offset in range(0, len(keys), 500):
            overwritten += len(
                list(
                    self.session.execute(
                        select(PhysicalBar.symbol, PhysicalBar.trading_day).where(
                            tuple_(PhysicalBar.symbol, PhysicalBar.trading_day).in_(
                                keys[offset : offset + 500]
                            )
                        )
                    )
                )
            )
        values = self.storage.encode(self.session, values)
        for offset in range(0, len(values), 500):
            self.session.execute(
                self.storage.upsert(),
                values[offset : offset + 500],
            )
        days = sorted({day for _, day in keys})
        calendar_insert = insert(cast(Table, TradingDayModel.__table__))
        calendar_upsert = calendar_insert.on_duplicate_key_update(
            trading_day=calendar_insert.inserted.trading_day
        )
        for offset in range(0, len(days), 500):
            self.session.execute(
                calendar_upsert, [{"trading_day": day} for day in days[offset : offset + 500]]
            )
        self.session.commit()
        return overwritten

    def bar_coverage(self, symbols: list[str] | None = None) -> dict[str, dict[str, Any]]:
        statement = bar_coverage_statement(Bar=self.storage.physical)
        if symbols is not None:
            statement = statement.where(self.storage.physical.symbol.in_(symbols))
        rows = cast(Iterable[tuple[str, date, date, int]], self.session.execute(statement))
        return {
            symbol: {"first_day": first, "last_day": last, "count": count}
            for symbol, first, last, count in rows
        }

    def bar_bounds(self) -> dict[str, dict[str, Any]]:
        # 没有 COUNT 才能利用 MIN/MAX 的 loose index scan 跳到每个标的端点。
        rows = cast(
            Iterable[tuple[str, date, date]],
            self.session.execute(
                bar_coverage_statement(include_count=False, Bar=self.storage.physical)
            ),
        )
        return {symbol: {"first_day": first, "last_day": last} for symbol, first, last in rows}

    def bar_adjustment(self, symbol: str) -> str | None:
        Bar = self.storage.logical
        adjustments = set(
            self.session.scalars(select(Bar.adjustment).where(Bar.symbol == symbol).distinct())
        )
        if None in adjustments:
            raise RuntimeError("日线来源引用缺失，拒绝推断复权口径")
        return _single_bar_adjustment(symbol, adjustments)

    def upsert_instruments(self, rows: list[dict[str, Any]]) -> None:
        suspended_symbols = set(
            self.session.scalars(
                select(InstrumentModel.symbol).where(InstrumentModel.status == "suspended")
            )
        )
        for item in rows:
            listed_on = item.get("listed_on")
            symbol = str(item["symbol"])
            status = str(item.get("status", "active"))
            if symbol in suspended_symbols and status == "active":
                status = "suspended"
            self.session.merge(
                InstrumentModel(
                    symbol=symbol,
                    name=str(item.get("name", "")),
                    exchange=str(item["exchange"]),
                    listed_on=date.fromisoformat(str(listed_on)) if listed_on else None,
                    status=status,
                )
            )
        self.session.commit()

    def set_instrument_status(self, symbol: str, status: str) -> bool:
        row = self.session.get(InstrumentModel, symbol)
        if row is None:
            return False
        row.status = status
        self.session.commit()
        return True

    def set_instrument_statuses(self, symbols: list[str], status: str) -> None:
        if not symbols:
            return
        self.session.query(InstrumentModel).filter(InstrumentModel.symbol.in_(symbols)).update(
            {InstrumentModel.status: status}, synchronize_session=False
        )
        self.session.commit()

    def mark_missing_instruments_delisted(self, active_symbols: set[str]) -> None:
        self.session.query(InstrumentModel).filter(
            InstrumentModel.symbol.not_in(active_symbols),
            InstrumentModel.status != "delisted",
            ~InstrumentModel.symbol.like("sh%"),
            ~InstrumentModel.symbol.like("sz%"),
        ).update({InstrumentModel.status: "delisted"}, synchronize_session=False)
        self.session.commit()

    def list_bars(
        self,
        start_day: date | None = None,
        end_day: date | None = None,
        symbol: str | None = None,
    ):
        Bar = self.storage.logical
        statement = select(Bar)
        if start_day is not None:
            statement = statement.where(Bar.trading_day >= start_day)
        if end_day is not None:
            statement = statement.where(Bar.trading_day <= end_day)
        if symbol is not None:
            statement = statement.where(Bar.symbol == symbol)
        if start_day is not None and symbol is None:
            statement = statement.with_hint(
                self.storage.table, "FORCE INDEX (ix_daily_bars_day_symbol)", dialect_name="mysql"
            )
        statement = statement.order_by(Bar.trading_day)
        return [self._snapshot_row(row) for row in self.session.scalars(statement)]

    def list_runtime_bars(self, start_day: date, end_day: date) -> list[dict[str, Any]]:
        symbols = list(
            self.session.scalars(
                runtime_symbols_statement(start_day, end_day, self.storage.physical)
            )
        )
        rows: list[dict[str, Any]] = []
        for offset in range(0, len(symbols), RUNTIME_SYMBOL_BATCH):
            batch = symbols[offset : offset + RUNTIME_SYMBOL_BATCH]
            result = self.session.execute(
                runtime_batch_statement(batch, start_day, end_day, self.storage.physical)
            )
            rows.extend(
                {
                    "symbol": symbol,
                    "trading_day": trading_day.isoformat(),
                    "available_at": available_at.isoformat(),
                    "open": str(open_price),
                    "high": str(high),
                    "low": str(low),
                    "close": str(close),
                }
                for symbol, trading_day, available_at, open_price, high, low, close in result
            )
        rows.sort(key=lambda row: (str(row["trading_day"]), str(row["symbol"])))
        return rows

    def iter_runtime_bars(self, start_day: date, end_day: date) -> Iterator[dict[str, Any]]:
        cursor = start_day
        while cursor <= end_day:
            last_day_of_month = date(
                cursor.year, cursor.month, monthrange(cursor.year, cursor.month)[1]
            )
            chunk_end = min(end_day, last_day_of_month)
            yield from self.list_runtime_bars(cursor, chunk_end)
            cursor = chunk_end + timedelta(days=1)

    def iter_snapshot_bars(self, start_day: date, end_day: date) -> Iterator[dict[str, Any]]:
        Bar = self.storage.logical
        # 只定位区间内代码，再读对应主键范围；长区间也不扫描区间外整张聚簇表。
        symbols = list(
            self.session.scalars(
                runtime_symbols_statement(start_day, end_day, self.storage.physical)
            )
        )
        statements = (
            select(Bar)
            .with_hint(self.storage.table, "FORCE INDEX (PRIMARY)", dialect_name="mysql")
            .where(
                Bar.symbol.in_(symbols[offset : offset + RUNTIME_SYMBOL_BATCH]),
                Bar.trading_day >= start_day,
                Bar.trading_day <= end_day,
            )
            .order_by(Bar.symbol, Bar.trading_day)
            .execution_options(yield_per=1000)
            for offset in range(0, len(symbols), RUNTIME_SYMBOL_BATCH)
        )
        for statement in statements:
            for row in self.session.scalars(statement):
                yield self._snapshot_row(row)

    @staticmethod
    def _snapshot_row(row: Any) -> dict[str, Any]:
        if row.source is None or row.adjustment is None:
            raise RuntimeError("日线来源引用缺失，拒绝生成快照")
        return {
            "symbol": row.symbol,
            "trading_day": row.trading_day.isoformat(),
            "open": str(row.open),
            "high": str(row.high),
            "low": str(row.low),
            "close": str(row.close),
            "volume": str(row.volume),
            "available_at": row.available_at.isoformat(),
            "amount": str(row.amount) if row.amount is not None else None,
            "source": row.source,
            "adjustment": row.adjustment,
            "archive_sha256": row.archive_sha256,
        }

    def list_instruments(self):
        return [
            {
                "symbol": row.symbol,
                "name": row.name,
                "exchange": row.exchange,
                "listed_on": row.listed_on.isoformat() if row.listed_on else None,
                "status": row.status,
            }
            for row in self.session.scalars(select(InstrumentModel))
        ]

    def get_instrument(self, symbol: str):
        row = self.session.get(InstrumentModel, symbol)
        return (
            None
            if row is None
            else {
                "symbol": row.symbol,
                "name": row.name,
                "exchange": row.exchange,
                "listed_on": row.listed_on.isoformat() if row.listed_on else None,
                "status": row.status,
            }
        )

    def coverage_page(
        self,
        *,
        page: int,
        page_size: int,
        search: str = "",
        status: str = "",
        after_symbol: str = "",
        before_symbol: str = "",
        target_day: date | None = None,
    ):
        Bar = self.storage.physical
        # 页码跳转仅跳过主键；详情和日线聚合只读取选中的一页。
        symbols = select(InstrumentModel.symbol)
        if status == "已退市":
            symbols = symbols.where(InstrumentModel.status == "delisted")
        elif status == "已停牌":
            symbols = symbols.where(InstrumentModel.status == "suspended")
        elif status:
            coverage = (
                select(
                    Bar.symbol.label("symbol"),
                    func.min(Bar.trading_day).label("first_day"),
                    func.max(Bar.trading_day).label("last_day"),
                )
                .with_hint(Bar, "FORCE INDEX (ix_daily_bars_coverage)", dialect_name="mysql")
                .group_by(Bar.symbol)
                .subquery()
            )
            days = func.datediff(coverage.c.last_day, coverage.c.first_day)
            status_expr = case(
                (coverage.c.first_day.is_(None), "未同步"),
                *([(coverage.c.last_day < target_day, "数据落后")] if target_day else []),
                (days >= 3652, "完全同步"),
                (days >= 1095, "部分同步"),
                else_="数据不足",
            )
            symbols = symbols.outerjoin(
                coverage, InstrumentModel.symbol == coverage.c.symbol
            ).where(status_expr == status, InstrumentModel.status == "active")
        if search:
            pattern = f"%{search}%"
            symbols = symbols.where(
                or_(InstrumentModel.symbol.like(pattern), InstrumentModel.name.like(pattern))
            )
        instrument_count = (
            self.session.scalar(select(func.count()).select_from(InstrumentModel)) or 0
        )
        if status:
            # 状态由日线首末日期决定；单次查询取至多约 6,000 个代码，避免重复聚合。
            matching = list(self.session.scalars(symbols.order_by(InstrumentModel.symbol)))
            total = len(matching)
            page = min(page, max(1, (total + page_size - 1) // page_size))
            if after_symbol:
                selected_symbols = matching[bisect_right(matching, after_symbol) :][:page_size]
            elif before_symbol:
                selected_symbols = matching[: bisect_left(matching, before_symbol)][-page_size:]
            else:
                selected_symbols = matching[(page - 1) * page_size : page * page_size]
        else:
            total = self.session.scalar(select(func.count()).select_from(symbols.subquery())) or 0
            page = min(page, max(1, (total + page_size - 1) // page_size))
            if after_symbol:
                page_query = symbols.where(InstrumentModel.symbol > after_symbol).order_by(
                    InstrumentModel.symbol
                )
            elif before_symbol:
                page_query = symbols.where(InstrumentModel.symbol < before_symbol).order_by(
                    InstrumentModel.symbol.desc()
                )
            else:
                page_query = symbols.order_by(InstrumentModel.symbol).offset((page - 1) * page_size)
            selected_symbols = list(self.session.scalars(page_query.limit(page_size)))
            if before_symbol:
                selected_symbols.reverse()
        if not selected_symbols:
            return instrument_count, total, page, []

        selected = {
            row.symbol: row
            for row in self.session.scalars(
                select(InstrumentModel).where(InstrumentModel.symbol.in_(selected_symbols))
            )
        }
        coverage_rows = self.session.execute(
            select(
                Bar.symbol,
                func.min(Bar.trading_day),
                func.max(Bar.trading_day),
                func.count(),
            )
            .with_hint(Bar, "FORCE INDEX (ix_daily_bars_coverage)", dialect_name="mysql")
            .where(Bar.symbol.in_(selected_symbols))
            .group_by(Bar.symbol)
        )
        selected_coverage = {
            symbol: {"first_day": first, "last_day": last, "count": count}
            for symbol, first, last, count in coverage_rows
        }
        rows = []
        for symbol in selected_symbols:
            instrument = selected[symbol]
            rows.append(
                {
                    "symbol": symbol,
                    "name": instrument.name,
                    "exchange": instrument.exchange,
                    "listed_on": instrument.listed_on.isoformat() if instrument.listed_on else None,
                    "status": instrument.status,
                    **selected_coverage.get(symbol, {}),
                }
            )
        return instrument_count, total, page, rows

    def list_trading_days(self) -> set[date]:
        return set(self.session.scalars(select(TradingDayModel.trading_day)))

    def upsert_trading_days(self, days: list[date]) -> None:
        values = sorted(set(days))
        statement = insert(cast(Table, TradingDayModel.__table__))
        statement = statement.on_duplicate_key_update(trading_day=statement.inserted.trading_day)
        for offset in range(0, len(values), 500):
            self.session.execute(
                statement, [{"trading_day": day} for day in values[offset : offset + 500]]
            )
        self.session.commit()

    def upsert_records(self, dataset_key: str, rows: list[dict[str, Any]]) -> int:
        overwritten = 0
        for item in rows:
            key = str(item["record_key"])
            overwritten += int(
                self.session.get(JsonMarketRecordModel, (dataset_key, key)) is not None
            )
            self.session.merge(
                JsonMarketRecordModel(
                    dataset_key=dataset_key,
                    record_key=key,
                    payload_json=json.dumps(item, ensure_ascii=False, default=str),
                    available_at=datetime.fromisoformat(str(item["available_at"])),
                )
            )
        self.session.commit()
        return overwritten

    def list_records(self, dataset_key: str, symbol: str | None = None):
        rows = self.session.scalars(
            select(JsonMarketRecordModel).where(JsonMarketRecordModel.dataset_key == dataset_key)
        )
        values = [json.loads(row.payload_json) for row in rows]
        return [row for row in values if symbol is None or row.get("symbol") == symbol]


class InMemoryBacktestStore:
    def __init__(self, rows: dict[str, dict[str, Any]]) -> None:
        self.rows = rows

    def save(self, run: dict[str, Any], snapshot_payload: bytes | SnapshotSpool) -> None:
        self.rows[str(run["id"])] = run

    def create_with_job(self, run: dict[str, Any], job: Job, jobs: Any) -> None:
        run_id = str(run["id"])
        self.rows[run_id] = run
        try:
            jobs.enqueue(job)
        except Exception:
            self.rows.pop(run_id, None)
            raise

    def get(self, run_id: str) -> dict[str, Any] | None:
        return self.rows.get(run_id)

    def mark_failed(self, run_id: str, message: str) -> None:
        run = self.rows[run_id]
        run.update({"status": "failed", "progress": 100, "error": message})

    def mark_running(self, run_id: str) -> None:
        self.rows[run_id].update({"status": "running", "progress": 5})

    def update_status(self, run_id: str, updates: dict[str, Any]) -> None:
        self.rows[run_id].update(updates)

    def list_for_owner(self, owner_id: str) -> list[dict[str, Any]]:
        return [row for row in self.rows.values() if row["owner_id"] == owner_id]


class SqlAlchemyBacktestStore:
    def __init__(
        self, session: Session, status_sessions: Callable[[], Session] | None = None
    ) -> None:
        self.session = session
        self.status_sessions = status_sessions

    def create_with_job(self, run: dict[str, Any], job: Job, _jobs: Any) -> None:
        if self.status_sessions is None:
            raise RuntimeError("回测提交需要独立事务 Session")
        with self.status_sessions() as session, session.begin():
            SqlAlchemyBacktestStore(session).save(run, b"[]", commit=False)
            SqlAlchemyJobRepository(session).enqueue(job, commit=False)

    def save(
        self, run: dict[str, Any], snapshot_payload: bytes | SnapshotSpool, *, commit: bool = True
    ) -> None:
        snapshot_id = str(run["snapshot_id"])
        if self.session.get(DataSnapshotModel, snapshot_id) is None:
            count = (
                snapshot_payload.record_count
                if isinstance(snapshot_payload, SnapshotSpool)
                else len(json.loads(snapshot_payload))
            )
            self.session.add(
                DataSnapshotModel(
                    id=snapshot_id,
                    content_sha256=snapshot_id,
                    record_count=count,
                )
            )
            # 模型未声明 ORM relationship，先写入父记录再添加外键分块。
            # flush 保留在当前事务中，不提前提交快照。
            self.session.flush()
            chunks = (
                streamed_snapshot_chunks(snapshot_payload)
                if isinstance(snapshot_payload, SnapshotSpool)
                else snapshot_chunks(snapshot_payload)
            )
            for sequence, chunk in enumerate(chunks):
                self.session.add(
                    DataSnapshotChunkModel(
                        snapshot_id=snapshot_id,
                        sequence=sequence,
                        payload=chunk,
                    )
                )
                if sequence % 100 == 99:
                    self.session.flush()
        row = self.session.get(BacktestRunModel, str(run["id"]))
        if row is None:
            row = BacktestRunModel(
                id=str(run["id"]),
                owner_id=str(run["owner_id"]),
                strategy_version_id=str(run["strategy_version_id"]),
                snapshot_id=snapshot_id,
                status=str(run["status"]),
                progress=int(run["progress"]),
                config_json=json.dumps(run["config"], ensure_ascii=False, default=str),
                payload_json=json.dumps(run, ensure_ascii=False, default=str),
                created_at=datetime.fromisoformat(str(run["created_at"])),
            )
            self.session.add(row)
        else:
            row.snapshot_id = snapshot_id
            row.status = str(run["status"])
            row.progress = int(run["progress"])
            row.config_json = json.dumps(run["config"], ensure_ascii=False, default=str)
            row.payload_json = json.dumps(run, ensure_ascii=False, default=str)
            self.session.execute(
                delete(BacktestPeriodModel).where(BacktestPeriodModel.run_id == row.id)
            )
            self.session.execute(
                delete(SimulatedTradeModel).where(SimulatedTradeModel.run_id == row.id)
            )
            self.session.execute(
                delete(BacktestMetricModel).where(BacktestMetricModel.run_id == row.id)
            )
        # 新建运行的结果明细同样依赖父记录；不能依赖 mapper 的默认顺序。
        self.session.flush()
        for item in run.get("periods", []):
            self.session.add(
                BacktestPeriodModel(
                    run_id=str(run["id"]),
                    trading_day=date.fromisoformat(item["trading_day"]),
                    equity=Decimal(item["equity"]),
                    cash=Decimal(item["cash"]),
                )
            )
        for sequence, item in enumerate(run.get("trades", [])):
            self.session.add(
                SimulatedTradeModel(
                    run_id=str(run["id"]),
                    sequence=sequence,
                    symbol=item["symbol"],
                    payload_json=json.dumps(item, ensure_ascii=False),
                )
            )
        for name, value in run.get("metrics", {}).items():
            self.session.add(
                BacktestMetricModel(
                    run_id=str(run["id"]),
                    name=name,
                    value=Decimal(value) if value is not None else None,
                )
            )
        if commit:
            self.session.commit()

    def mark_failed(self, run_id: str, message: str) -> None:
        self.update_status(run_id, {"status": "failed", "progress": 100, "error": message})

    def mark_running(self, run_id: str) -> None:
        self.update_status(run_id, {"status": "running", "progress": 5})

    def update_status(self, run_id: str, updates: dict[str, Any]) -> None:
        # 独立短事务，不能提交行情读取事务或复用已失效的读连接。
        scope = self.status_sessions() if self.status_sessions else nullcontext(self.session)
        with scope as session:
            row = session.get(BacktestRunModel, run_id)
            if row is None:
                return
            payload = json.loads(row.payload_json)
            payload.update(updates)
            row.status = str(payload["status"])
            row.progress = int(payload["progress"])
            row.payload_json = json.dumps(payload, ensure_ascii=False, default=str)
            session.commit()

    def get(self, run_id: str) -> dict[str, Any] | None:
        row = self.session.get(BacktestRunModel, run_id)
        return None if row is None else json.loads(row.payload_json)

    def list_for_owner(self, owner_id: str) -> list[dict[str, Any]]:
        rows = self.session.scalars(
            select(BacktestRunModel)
            .where(BacktestRunModel.owner_id == owner_id)
            .order_by(BacktestRunModel.created_at.desc())
        )
        return [json.loads(row.payload_json) for row in rows]

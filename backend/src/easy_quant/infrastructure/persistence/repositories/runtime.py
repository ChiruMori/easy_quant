from __future__ import annotations

import gzip
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from easy_quant.domain.shared.errors import StateConflictError
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

    def bar_coverage(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for row in self.daily_bars.values():
            symbol = str(row["symbol"])
            day = date.fromisoformat(str(row["trading_day"]))
            item = result.setdefault(symbol, {"first_day": day, "last_day": day, "count": 0})
            item["first_day"] = min(item["first_day"], day)
            item["last_day"] = max(item["last_day"], day)
            item["count"] += 1
        return result

    def upsert_instruments(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            self.instruments[str(row["symbol"])] = row

    def list_bars(self, start_day: date | None = None, end_day: date | None = None):
        return [
            row
            for row in self.daily_bars.values()
            if (start_day is None or date.fromisoformat(str(row["trading_day"])) >= start_day)
            and (end_day is None or date.fromisoformat(str(row["trading_day"])) <= end_day)
        ]

    def list_instruments(self):
        return list(self.instruments.values())

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

    def upsert_bars(self, rows: list[dict[str, Any]]) -> int:
        incoming = {str(row["symbol"]): str(row.get("adjustment", "unknown")) for row in rows}
        if incoming:
            existing = self.session.execute(
                select(DailyBarModel.symbol, DailyBarModel.adjustment)
                .where(DailyBarModel.symbol.in_(incoming))
                .distinct()
            )
            for symbol, adjustment in existing:
                if adjustment != incoming[symbol]:
                    raise StateConflictError("日线复权口径冲突，拒绝混合写入", {"symbol": symbol})
        overwritten = 0
        for item in rows:
            symbol, day = str(item["symbol"]), date.fromisoformat(str(item["trading_day"]))
            overwritten += int(self.session.get(DailyBarModel, (symbol, day)) is not None)
            row = DailyBarModel(
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
            self.session.merge(row)
            self.session.merge(TradingDayModel(trading_day=day))
        self.session.commit()
        return overwritten

    def bar_coverage(self) -> dict[str, dict[str, Any]]:
        statement = select(
            DailyBarModel.symbol,
            func.min(DailyBarModel.trading_day),
            func.max(DailyBarModel.trading_day),
            func.count(),
        ).group_by(DailyBarModel.symbol)
        return {
            symbol: {"first_day": first, "last_day": last, "count": count}
            for symbol, first, last, count in self.session.execute(statement)
        }

    def upsert_instruments(self, rows: list[dict[str, Any]]) -> None:
        for item in rows:
            listed_on = item.get("listed_on")
            self.session.merge(
                InstrumentModel(
                    symbol=str(item["symbol"]),
                    name=str(item.get("name", "")),
                    exchange=str(item["exchange"]),
                    listed_on=date.fromisoformat(str(listed_on)) if listed_on else None,
                    status=str(item.get("status", "active")),
                )
            )
        self.session.commit()

    def list_bars(self, start_day: date | None = None, end_day: date | None = None):
        statement = select(DailyBarModel)
        if start_day is not None:
            statement = statement.where(DailyBarModel.trading_day >= start_day)
        if end_day is not None:
            statement = statement.where(DailyBarModel.trading_day <= end_day)
        return [
            {
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
            for row in self.session.scalars(statement)
        ]

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

    def list_trading_days(self) -> set[date]:
        return set(self.session.scalars(select(TradingDayModel.trading_day)))

    def upsert_trading_days(self, days: list[date]) -> None:
        for day in days:
            self.session.merge(TradingDayModel(trading_day=day))
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

    def save(self, run: dict[str, Any], snapshot_payload: bytes) -> None:
        self.rows[str(run["id"])] = run

    def get(self, run_id: str) -> dict[str, Any] | None:
        return self.rows.get(run_id)

    def list_for_owner(self, owner_id: str) -> list[dict[str, Any]]:
        return [row for row in self.rows.values() if row["owner_id"] == owner_id]


class SqlAlchemyBacktestStore:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, run: dict[str, Any], snapshot_payload: bytes) -> None:
        snapshot_id = str(run["snapshot_id"])
        if self.session.get(DataSnapshotModel, snapshot_id) is None:
            self.session.add(
                DataSnapshotModel(
                    id=snapshot_id,
                    content_sha256=snapshot_id,
                    record_count=len(json.loads(snapshot_payload)),
                )
            )
            self.session.add(
                DataSnapshotChunkModel(
                    snapshot_id=snapshot_id,
                    sequence=0,
                    payload=gzip.compress(snapshot_payload, mtime=0),
                )
            )
        self.session.add(
            BacktestRunModel(
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
        )
        for item in run["periods"]:
            self.session.add(
                BacktestPeriodModel(
                    run_id=str(run["id"]),
                    trading_day=date.fromisoformat(item["trading_day"]),
                    equity=Decimal(item["equity"]),
                    cash=Decimal(item["cash"]),
                )
            )
        for sequence, item in enumerate(run["trades"]):
            self.session.add(
                SimulatedTradeModel(
                    run_id=str(run["id"]),
                    sequence=sequence,
                    symbol=item["symbol"],
                    payload_json=json.dumps(item, ensure_ascii=False),
                )
            )
        for name, value in run["metrics"].items():
            self.session.add(
                BacktestMetricModel(
                    run_id=str(run["id"]),
                    name=name,
                    value=Decimal(value) if value is not None else None,
                )
            )
        self.session.commit()

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

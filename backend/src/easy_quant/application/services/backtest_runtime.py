from __future__ import annotations

import heapq
import logging
import time as clock
from collections import deque
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from itertools import groupby
from typing import Any
from zoneinfo import ZoneInfo

from easy_quant.application.services.strategy_validation import (
    extract_factor_dependencies,
    extract_history_trading_days,
)
from easy_quant.domain.backtesting.engine import PhasedBacktestSession
from easy_quant.domain.backtesting.entities import BacktestConfig
from easy_quant.domain.backtesting.execution import MarketBar
from easy_quant.domain.market_data.calendar import TradingCalendar
from easy_quant.domain.shared.errors import StateConflictError
from easy_quant.domain.strategies.entities import Signal
from easy_quant.infrastructure.persistence.snapshot_spool import SnapshotSpool
from easy_quant.infrastructure.strategy_runtime.runner import StreamingStrategyRunner

logger = logging.getLogger(__name__)


def execute_backtest(container: Any, run_id: str) -> dict[str, object]:
    run = container.backtests.get(run_id)
    if run is None:
        raise StateConflictError("回测记录不存在")
    payload = run["config"]
    strategy_version_id = str(run["strategy_version_id"])
    definition = next(
        (
            item
            for item in container.state.strategies.definitions.values()
            if item.owner_id == run["owner_id"]
            and any(
                version.id == strategy_version_id
                for version in container.state.strategies.versions(item.id)
            )
        ),
        None,
    )
    if definition is None:
        raise StateConflictError("策略版本不存在或不属于当前用户")
    version = next(
        item
        for item in container.state.strategies.versions(definition.id)
        if item.id == strategy_version_id
    )
    start_day = date.fromisoformat(str(payload["start_day"]))
    end_day = date.fromisoformat(str(payload["end_day"]))
    dependencies = extract_factor_dependencies(version.source_code)
    generic_missing = [
        dataset
        for dataset in sorted(dependencies - {"daily-bars"})
        if not container.market_data.list_records(dataset)
    ]
    if generic_missing:
        raise StateConflictError(
            "策略依赖的数据尚未同步",
            {
                "missing_data": [
                    {
                        "dataset": dataset,
                        "start_day": start_day.isoformat(),
                        "end_day": end_day.isoformat(),
                    }
                    for dataset in generic_missing
                ],
                "action_url": "/admin/data/acquisitions",
            },
        )
    coverage: dict[str, tuple[date, date]] = {}
    calendar = TradingCalendar(container.market_data.list_trading_days() or None)
    expected_days = [
        start_day + timedelta(days=offset)
        for offset in range((end_day - start_day).days + 1)
        if calendar.is_trading_day(start_day + timedelta(days=offset))
    ]
    if not expected_days:
        raise StateConflictError("所选区间不包含交易日")
    expected_start, expected_end = expected_days[0], expected_days[-1]
    config = BacktestConfig(
        strategy_version_id,
        (),
        start_day,
        end_day,
        Decimal(str(payload["initial_cash"])),
        Decimal(str(payload.get("fee_rate", "0.0003"))),
        Decimal(str(payload.get("slippage_rate", "0.0001"))),
        payload.get("benchmark"),
        int(payload.get("random_seed", 0)),
    )
    generic_records = {
        dataset: container.market_data.list_records(dataset)
        for dataset in dependencies - {"daily-bars"}
    }

    def visible_records(cutoff: datetime) -> dict[str, dict[str, list[dict[str, object]]]]:
        records: dict[str, dict[str, list[dict[str, object]]]] = {}
        for dataset, rows in generic_records.items():
            for row in rows:
                raw_available_at = row.get("available_at")
                if not raw_available_at:
                    continue
                if datetime.fromisoformat(str(raw_available_at)).astimezone(UTC) > cutoff:
                    continue
                records.setdefault(dataset, {}).setdefault(str(row.get("symbol", "")), []).append(
                    row
                )
        return records

    phases = ("before_market", "on_market", "after_market")
    strategy_outputs = []
    history_window = extract_history_trading_days(version.source_code)
    backtest_session = PhasedBacktestSession(config)
    recent_days: deque[date] = deque(maxlen=history_window + 1)
    pending: list[tuple[datetime, int, dict[str, object]]] = []
    sequence = 0
    row_count = 0
    day_count = 0
    started = clock.monotonic()

    def due_rows(cutoff: datetime, earliest_day: date) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        while pending and pending[0][0] <= cutoff:
            _, _, row = heapq.heappop(pending)
            if date.fromisoformat(str(row["trading_day"])) >= earliest_day:
                rows.append(row)
        return rows

    rows = container.market_data.iter_runtime_bars(start_day, end_day)
    with StreamingStrategyRunner(version, {}, timeout_seconds=30) as runner:
        for trading_day_text, day_group in groupby(rows, key=lambda row: str(row["trading_day"])):
            trading_day = date.fromisoformat(trading_day_text)
            today_rows = list(day_group)
            row_count += len(today_rows)
            day_count += 1
            recent_days.append(trading_day)
            expire_before = recent_days[0]
            for row in today_rows:
                symbol = str(row["symbol"])
                first, last = coverage.get(symbol, (trading_day, trading_day))
                coverage[symbol] = min(first, trading_day), max(last, trading_day)
            before_cutoff = datetime.combine(
                trading_day, time(9), ZoneInfo("Asia/Shanghai")
            ).astimezone(UTC)
            after_cutoff = datetime.combine(
                trading_day, time(23, 59, 59), ZoneInfo("Asia/Shanghai")
            ).astimezone(UTC)
            prior_before = due_rows(before_cutoff, expire_before)
            prior_after = due_rows(after_cutoff, expire_before)
            today_after = []
            for row in today_rows:
                available_at = datetime.fromisoformat(str(row["available_at"])).astimezone(UTC)
                if available_at <= after_cutoff:
                    today_after.append(row)
                else:
                    heapq.heappush(pending, (available_at, sequence, row))
                    sequence += 1
            records_before = visible_records(before_cutoff)
            results = runner.run_day(
                trading_day,
                expire_before=expire_before,
                prior_before=prior_before,
                prior_after=prior_after,
                today_after=today_after,
                today_symbols=sorted({str(row["symbol"]) for row in today_rows}),
                current_prices={str(row["symbol"]): float(str(row["open"])) for row in today_rows},
                records={
                    "before_market": records_before,
                    "on_market": records_before,
                    "after_market": visible_records(after_cutoff),
                },
            )
            for phase, result in zip(phases, results, strict=True):
                if result.status != "succeeded":
                    raise StateConflictError(
                        "策略运行失败",
                        {
                            "phase": phase,
                            "trading_day": trading_day.isoformat(),
                            "error": result.error,
                        },
                    )
                if result.stdout:
                    strategy_outputs.append(
                        {
                            "trading_day": trading_day.isoformat(),
                            "phase": phase,
                            "text": result.stdout,
                        }
                    )
            day_bars = [
                MarketBar(
                    trading_day,
                    str(row["symbol"]),
                    Decimal(str(row["close"])),
                    True,
                    Decimal(str(row["open"])),
                    Decimal(str(row["high"])),
                    Decimal(str(row["low"])),
                )
                for row in today_rows
            ]
            signals_by_phase: dict[str, list[Signal]] = dict(
                zip(phases, (result.signals for result in results), strict=True)
            )
            backtest_session.advance(
                trading_day, day_bars, lambda phase, signals=signals_by_phase: signals[phase]
            )

    if not row_count:
        raise StateConflictError(
            "回测所需行情数据尚未同步",
            {
                "action_url": "/admin/data",
                "start_day": start_day.isoformat(),
                "end_day": end_day.isoformat(),
            },
        )
    missing = [
        {
            "dataset": "日线 K 线",
            "symbol": symbol,
            "start_day": expected_start.isoformat(),
            "end_day": expected_end.isoformat(),
            "available_start": available_start.isoformat(),
            "available_end": available_end.isoformat(),
        }
        for symbol, (available_start, available_end) in coverage.items()
        if available_start > expected_start or available_end < expected_end
    ]
    if missing:
        raise StateConflictError(
            "部分策略标的行情覆盖不足，回测已阻止",
            {"missing_data": missing, "action_url": "/admin/data"},
        )
    periods, trades, metrics = backtest_session.finish()
    logger.info(
        "回测策略阶段完成 run_id=%s days=%d rows=%d elapsed_seconds=%.3f",
        run_id,
        day_count,
        row_count,
        clock.monotonic() - started,
    )
    with SnapshotSpool() as snapshot:
        for row in container.market_data.iter_snapshot_bars(start_day, end_day):
            snapshot.append(row)
        snapshot_id = snapshot.finish()
        completed = {
            **run,
            "snapshot_id": snapshot_id,
            "status": "succeeded",
            "progress": 100,
            "metrics": {
                key: str(value) if value is not None else None for key, value in metrics.items()
            },
            "periods": [
                {
                    "trading_day": item.trading_day.isoformat(),
                    "equity": str(item.equity),
                    "cash": str(item.cash),
                }
                for item in periods
            ],
            "trades": [
                {
                    "trading_day": item.trading_day.isoformat(),
                    "symbol": item.symbol,
                    "action": item.action,
                    "quantity": str(item.quantity),
                    "price": str(item.price),
                    "fee": str(item.fee),
                }
                for item in trades
            ],
            "assumptions": {
                "frequency": "daily",
                "fee_rate": str(config.fee_rate),
                "slippage_rate": str(config.slippage_rate),
            },
            "strategy_outputs": strategy_outputs,
        }
        container.backtests.save(completed, snapshot)
    logger.info(
        "回测快照保存完成 run_id=%s days=%d rows=%d elapsed_seconds=%.3f",
        run_id,
        day_count,
        row_count,
        clock.monotonic() - started,
    )
    return {"status": "succeeded", "backtest_id": run_id, "progress": 100}

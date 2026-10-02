from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from easy_quant.application.services.strategy_validation import extract_factor_dependencies
from easy_quant.domain.backtesting.engine import run_phased_daily_backtest
from easy_quant.domain.backtesting.entities import BacktestConfig
from easy_quant.domain.backtesting.execution import MarketBar
from easy_quant.domain.market_data.calendar import TradingCalendar
from easy_quant.domain.shared.errors import StateConflictError
from easy_quant.infrastructure.strategy_runtime.runner import SubprocessStrategyRunner


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
    stored_rows = container.market_data.list_bars(start_day, end_day)
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
    if not stored_rows:
        raise StateConflictError(
            "回测所需行情数据尚未同步",
            {
                "action_url": "/admin/data",
                "start_day": start_day.isoformat(),
                "end_day": end_day.isoformat(),
            },
        )
    symbols = sorted({str(row["symbol"]) for row in stored_rows})
    calendar = TradingCalendar(container.market_data.list_trading_days() or None)
    expected_days = [
        start_day + timedelta(days=offset)
        for offset in range((end_day - start_day).days + 1)
        if calendar.is_trading_day(start_day + timedelta(days=offset))
    ]
    if not expected_days:
        raise StateConflictError("所选区间不包含交易日")
    expected_start, expected_end = expected_days[0], expected_days[-1]
    missing = []
    for symbol in symbols:
        available_days = sorted(
            date.fromisoformat(str(row["trading_day"]))
            for row in stored_rows
            if row["symbol"] == symbol
        )
        if available_days[0] > expected_start or available_days[-1] < expected_end:
            missing.append(
                {
                    "dataset": "日线 K 线",
                    "symbol": symbol,
                    "start_day": expected_start.isoformat(),
                    "end_day": expected_end.isoformat(),
                    "available_start": available_days[0].isoformat(),
                    "available_end": available_days[-1].isoformat(),
                }
            )
    if missing:
        raise StateConflictError(
            "部分策略标的行情覆盖不足，回测已阻止",
            {"missing_data": missing, "action_url": "/admin/data"},
        )

    config = BacktestConfig(
        strategy_version_id,
        tuple(symbols),
        start_day,
        end_day,
        Decimal(str(payload["initial_cash"])),
        Decimal(str(payload.get("fee_rate", "0.0003"))),
        Decimal(str(payload.get("slippage_rate", "0.0001"))),
        payload.get("benchmark"),
        int(payload.get("random_seed", 0)),
    )
    bars = [
        MarketBar(
            date.fromisoformat(str(row["trading_day"])),
            str(row["symbol"]),
            Decimal(str(row["close"])),
            True,
            Decimal(str(row["open"])),
            Decimal(str(row["high"])),
            Decimal(str(row["low"])),
        )
        for row in stored_rows
    ]
    generic_records = {
        dataset: container.market_data.list_records(dataset)
        for dataset in dependencies - {"daily-bars"}
    }

    def context_for(trading_day: date, phase: str) -> dict[str, object]:
        visible_rows = [
            row
            for row in stored_rows
            if date.fromisoformat(str(row["trading_day"])) < trading_day
            or (phase == "after_market" and str(row["trading_day"]) == trading_day.isoformat())
        ]
        prices: dict[str, list[float]] = {}
        for row in sorted(visible_rows, key=lambda item: str(item["trading_day"])):
            prices.setdefault(str(row["symbol"]), []).append(float(str(row["close"])))
        cutoff = datetime.combine(
            trading_day,
            time(23, 59, 59) if phase == "after_market" else time(9),
            ZoneInfo("Asia/Shanghai"),
        ).astimezone(UTC)
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
        visible_symbols = {str(row["symbol"]) for row in visible_rows}
        if phase != "before_market":
            visible_symbols.update(
                str(row["symbol"])
                for row in stored_rows
                if str(row["trading_day"]) == trading_day.isoformat()
            )
        return {
            "universe": sorted(visible_symbols),
            "prices": prices,
            "market_values": {},
            "trading_day": trading_day.isoformat(),
            "phase": phase,
            "current_prices": {
                str(row["symbol"]): float(str(row["open"]))
                for row in stored_rows
                if str(row["trading_day"]) == trading_day.isoformat()
            }
            if phase == "on_market"
            else {},
            "records": records,
        }

    phases = ("before_market", "on_market", "after_market")
    phase_results = {}
    runner = SubprocessStrategyRunner(timeout_seconds=30)
    strategy_outputs = []
    for trading_day in sorted({bar.trading_day for bar in bars}):
        results = runner.run_many(
            version, {}, [(context_for(trading_day, phase), phase) for phase in phases]
        )
        for phase, result in zip(phases, results, strict=True):
            if result.status != "succeeded":
                raise StateConflictError(
                    "策略运行失败",
                    {"phase": phase, "trading_day": trading_day.isoformat(), "error": result.error},
                )
            phase_results[(trading_day, phase)] = result
            if result.stdout:
                strategy_outputs.append(
                    {"trading_day": trading_day.isoformat(), "phase": phase, "text": result.stdout}
                )

    def run_phase(trading_day: date, phase: str):
        return phase_results[(trading_day, phase)].signals

    periods, trades, metrics = run_phased_daily_backtest(config, bars, run_phase)
    completed = {
        **run,
        "snapshot_id": hashlib.sha256(
            json.dumps(stored_rows, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest(),
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
    container.backtests.save(
        completed, json.dumps(stored_rows, ensure_ascii=False, sort_keys=True).encode("utf-8")
    )
    return {"status": "succeeded", "backtest_id": run_id, "progress": 100}

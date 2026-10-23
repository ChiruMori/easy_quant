from __future__ import annotations

import hashlib
import heapq
import json
import logging
import time as clock
from collections import deque
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from itertools import groupby, islice
from typing import Any
from zoneinfo import ZoneInfo

from easy_quant.application.services.backtest_reporting import performance_rows
from easy_quant.application.services.instrument_eligibility import delisted_symbols
from easy_quant.application.services.run_profile import RunProfile
from easy_quant.application.services.strategy_validation import (
    extract_factor_dependencies,
    extract_history_trading_days,
)
from easy_quant.domain.backtesting.engine import PhasedBacktestSession
from easy_quant.domain.backtesting.entities import BacktestConfig
from easy_quant.domain.backtesting.execution import MarketBar
from easy_quant.domain.market_data.calendar import TradingCalendar
from easy_quant.domain.market_data.indices import INDEX_CATALOG, benchmark_symbol, is_index
from easy_quant.domain.shared.errors import StateConflictError
from easy_quant.domain.strategies.entities import Signal
from easy_quant.infrastructure.persistence.snapshot_spool import SnapshotSpool
from easy_quant.infrastructure.strategy_runtime.runner import StreamingStrategyRunner

logger = logging.getLogger(__name__)


def execute_backtest(
    container: Any, run_id: str, *, profile: RunProfile | None = None
) -> dict[str, object]:
    return _execute_backtest(container, run_id, profile or RunProfile())


def _execute_backtest(container: Any, run_id: str, profile: RunProfile) -> dict[str, object]:
    run = container.backtests.get(run_id)
    if run is None:
        raise StateConflictError("回测记录不存在")

    last_report = 0.0

    def report(
        stage: str, progress: int, *, day: date | None = None, hook: str = "", force: bool = False
    ) -> None:
        nonlocal last_report
        now = clock.monotonic()
        if force or now - last_report >= 2:
            container.backtests.update_status(
                run_id,
                {
                    "status": "running",
                    "progress": progress,
                    "execution": {
                        "stage": stage,
                        "trading_day": day.isoformat() if day else None,
                        "hook": hook,
                        "elapsed_seconds": profile.snapshot()["total_seconds"],
                    },
                    "timing": profile.snapshot(),
                },
            )
            logger.info(
                "回测进度 run_id=%s stage=%s progress=%d day=%s hook=%s elapsed_seconds=%.3f",
                run_id,
                stage,
                progress,
                day,
                hook,
                now - profile.started,
            )
            last_report = now

    report("validation", 5, force=True)
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
    excluded = delisted_symbols(container.market_data)
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
    calendar = TradingCalendar(container.market_data.list_trading_days() or None)
    expected_days = [
        start_day + timedelta(days=offset)
        for offset in range((end_day - start_day).days + 1)
        if calendar.is_trading_day(start_day + timedelta(days=offset))
    ]
    if not expected_days:
        raise StateConflictError("所选区间不包含交易日")
    expected_start, expected_end = expected_days[0], expected_days[-1]
    # 只读覆盖索引摘要，先报告缺失，避免跑完整策略后才阻止结果。
    coverage = container.market_data.bar_bounds()
    instruments = {str(item["symbol"]): item for item in container.market_data.list_instruments()}
    benchmark = benchmark_symbol(str(payload["benchmark"])) if payload.get("benchmark") else None
    benchmark_prices: dict[str, Decimal] = {}
    if benchmark:
        for row in container.market_data.list_bars(expected_start, expected_end, benchmark):
            day = date.fromisoformat(str(row["trading_day"]))
            cutoff = datetime.combine(day, time(23, 59, 59), ZoneInfo("Asia/Shanghai"))
            if datetime.fromisoformat(str(row["available_at"])) <= cutoff:
                price = Decimal(str(row["close"]))
                if price.is_finite() and price > 0:
                    benchmark_prices[day.isoformat()] = price
        if any(day.isoformat() not in benchmark_prices for day in expected_days):
            raise StateConflictError(
                "基准行情缺失或覆盖不足，请先同步指数日线",
                {
                    "action_url": "/admin/data?tab=indices"
                    if is_index(benchmark)
                    else "/admin/data/acquisitions",
                    "benchmark": benchmark,
                    "missing_data": [
                        {
                            "symbol": benchmark,
                            "start_day": expected_start.isoformat(),
                            "end_day": expected_end.isoformat(),
                        }
                    ],
                },
            )
    missing = []
    for symbol, item in coverage.items():
        if (
            symbol in excluded
            or is_index(symbol)
            or instruments.get(symbol, {}).get("status") == "suspended"
        ):
            continue
        available_start, available_end = item["first_day"], item["last_day"]
        # 原运行股票池来自区间内行情，完全不相交的历史/新上市证券不属于本次股票池。
        if available_start > expected_end or available_end < expected_start:
            continue
        listed_on = instruments.get(symbol, {}).get("listed_on")
        listed_day = date.fromisoformat(str(listed_on)) if listed_on else expected_start
        listed_days = [day for day in expected_days if day >= listed_day]
        if not listed_days:
            continue
        required_start = listed_days[0]
        if available_start > required_start or available_end < expected_end:
            missing.append(
                {
                    "dataset": "日线 K 线",
                    "symbol": symbol,
                    "start_day": required_start.isoformat(),
                    "end_day": expected_end.isoformat(),
                    "available_start": available_start.isoformat(),
                    "available_end": available_end.isoformat(),
                }
            )
    if not coverage:
        raise StateConflictError("回测所需行情数据尚未同步", {"action_url": "/admin/data"})
    if missing:
        raise StateConflictError(
            "部分策略标的行情覆盖不足，回测已阻止",
            {"missing_data": missing, "action_url": "/admin/data"},
        )
    config = BacktestConfig(
        strategy_version_id,
        (),
        start_day,
        end_day,
        Decimal(str(payload["initial_cash"])),
        Decimal(str(payload.get("fee_rate", "0.0003"))),
        Decimal(str(payload.get("slippage_rate", "0.0001"))),
        benchmark,
        int(payload.get("random_seed", 0)),
    )
    generic_records = {
        dataset: [
            row
            for row in container.market_data.list_records(dataset)
            if str(row.get("symbol", "")) not in excluded
        ]
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

    strategy_outputs = []
    history_window = extract_history_trading_days(version.source_code)
    backtest_session = PhasedBacktestSession(config)
    recent_days: deque[date] = deque(maxlen=history_window + 1)
    warmup_days = sorted(
        day for day in container.market_data.list_trading_days() if day < start_day
    )[-history_window:]
    history_start = warmup_days[0] if warmup_days else start_day
    profile.workload.update(
        history_start=history_start.isoformat(),
        start_day=start_day.isoformat(),
        end_day=end_day.isoformat(),
        history_trading_days=history_window,
        warmup_rows=0,
    )
    recent_days.extend(warmup_days)
    pending: list[tuple[datetime, int, dict[str, object]]] = []
    sequence = 0
    row_count = 0
    day_count = 0
    final_prices: dict[str, Decimal] = {}
    started = clock.monotonic()
    profile.enter("warmup")
    report("warmup", 10, force=True)
    for row in container.market_data.iter_runtime_bars(
        history_start, start_day - timedelta(days=1)
    ):
        if str(row["symbol"]) not in excluded:
            profile.workload["warmup_rows"] += 1
            available_at = datetime.fromisoformat(str(row["available_at"])).astimezone(UTC)
            heapq.heappush(pending, (available_at, sequence, row))
            sequence += 1
            report("warmup", 10)

    def due_rows(cutoff: datetime, earliest_day: date) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        while pending and pending[0][0] <= cutoff:
            _, _, row = heapq.heappop(pending)
            if date.fromisoformat(str(row["trading_day"])) >= earliest_day:
                rows.append(row)
        return rows

    profile.enter("loading_data")
    report("loading_data", 15, force=True)
    rows = (
        row
        for row in container.market_data.iter_runtime_bars(start_day, end_day)
        if str(row["symbol"]) not in excluded
    )
    with StreamingStrategyRunner(
        version, dict(payload.get("parameters", {})), timeout_seconds=30
    ) as runner:
        for trading_day_text, day_group in groupby(rows, key=lambda row: str(row["trading_day"])):
            trading_day = date.fromisoformat(trading_day_text)
            today_rows = list(day_group)
            profile.enter("strategy")
            row_count += len(today_rows)
            day_count += 1
            recent_days.append(trading_day)
            expire_before = recent_days[0]
            before_cutoff = datetime.combine(
                trading_day, time(9), ZoneInfo("Asia/Shanghai")
            ).astimezone(UTC)
            intraday_cutoff = datetime.combine(
                trading_day,
                time.fromisoformat(container.settings.intraday_run_time),
                ZoneInfo("Asia/Shanghai"),
            ).astimezone(UTC)
            after_cutoff = datetime.combine(
                trading_day, time(23, 59, 59), ZoneInfo("Asia/Shanghai")
            ).astimezone(UTC)
            prior_before = due_rows(before_cutoff, expire_before)
            prior_intraday = due_rows(intraday_cutoff, expire_before)
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

            today_symbols = sorted({str(row["symbol"]) for row in today_rows})
            current_prices = {
                str(row["symbol"]): str(
                    (Decimal(str(row["open"])) + Decimal(str(row["close"]))) / 2
                )
                for row in today_rows
            }
            phase_inputs: dict[str, dict[str, Any]] = {
                phase: {
                    "expire_before": expire_before,
                    "prior_before": prior_before if phase == "before_market" else [],
                    "prior_intraday": prior_intraday if phase == "on_market" else [],
                    "prior_after": prior_after if phase == "after_market" else [],
                    "today_after": today_after if phase == "after_market" else [],
                    "today_symbols": today_symbols,
                    "current_prices": current_prices if phase == "on_market" else {},
                    "records": {
                        phase: visible_records(after_cutoff)
                        if phase == "after_market"
                        else visible_records(intraday_cutoff)
                        if phase == "on_market"
                        else records_before
                    },
                    "decision_at": (
                        after_cutoff
                        if phase == "after_market"
                        else intraday_cutoff
                        if phase == "on_market"
                        else before_cutoff
                    ).isoformat(),
                }
                for phase in ("before_market", "on_market", "after_market")
            }

            def strategy(
                phase: str,
                day: date = trading_day,
                inputs: dict[str, dict[str, Any]] = phase_inputs,
                completed_days: int = day_count,
            ) -> list[Signal]:
                portfolio = backtest_session.portfolio
                progress = 15 + int(
                    70 * min(completed_days, len(expected_days)) / len(expected_days)
                )
                report(
                    "strategy",
                    progress,
                    day=day,
                    hook=phase,
                    force=completed_days == 1 and phase == "before_market",
                )
                hook_started = profile.timer()
                result = runner.run_phase(
                    day,
                    phase=phase,
                    positions={
                        symbol: str(quantity) for symbol, quantity in portfolio.positions.items()
                    },
                    cash=str(portfolio.cash),
                    costs={symbol: str(value) for symbol, value in portfolio.costs.items()},
                    fee_rate=str(config.fee_rate),
                    slippage_rate=str(config.slippage_rate),
                    **inputs[phase],
                )
                profile.record_hook(day.isoformat(), phase, hook_started)
                if result.status != "succeeded":
                    raise StateConflictError(
                        "策略运行失败",
                        {
                            "phase": phase,
                            "trading_day": day.isoformat(),
                            "error": result.error,
                        },
                    )
                if result.stdout:
                    strategy_outputs.append(
                        {
                            "trading_day": day.isoformat(),
                            "phase": phase,
                            "text": result.stdout,
                        }
                    )
                return [
                    signal
                    for signal in result.signals
                    if signal.symbol not in excluded and not is_index(signal.symbol)
                ]

            backtest_session.advance(trading_day, day_bars, strategy)
            final_prices = {bar.symbol: bar.close for bar in day_bars}
            report(
                "loading_data",
                15 + int(70 * min(day_count, len(expected_days)) / len(expected_days)),
                day=trading_day,
            )
            profile.enter("loading_data")

    if not row_count:
        raise StateConflictError(
            "回测所需行情数据尚未同步",
            {
                "action_url": "/admin/data",
                "start_day": start_day.isoformat(),
                "end_day": end_day.isoformat(),
            },
        )
    periods, trades, metrics = backtest_session.finish()
    benchmark_base = benchmark_prices.get(expected_start.isoformat())
    if benchmark_base is not None:
        metrics["benchmark_return"] = (
            benchmark_prices[expected_end.isoformat()] / benchmark_base - 1
        )

    logger.info(
        "回测策略阶段完成 run_id=%s days=%d rows=%d elapsed_seconds=%.3f",
        run_id,
        day_count,
        row_count,
        clock.monotonic() - started,
    )
    with SnapshotSpool() as snapshot:
        profile.enter("snapshot")
        report("snapshot", 90, force=True)
        source = iter(container.market_data.iter_snapshot_bars(history_start, end_day))
        read_seconds = encode_seconds = 0.0
        while True:
            batch_started = clock.monotonic()
            batch = list(islice(source, 1000))
            read_seconds += clock.monotonic() - batch_started
            if not batch:
                break
            batch_started = clock.monotonic()
            for row in batch:
                if str(row["symbol"]) not in excluded:
                    snapshot.append(row)
            encode_seconds += clock.monotonic() - batch_started
            profile.workload.update(
                snapshot_read_seconds=round(read_seconds, 3),
                snapshot_encode_seconds=round(encode_seconds, 3),
            )
            report("snapshot", 90)
        snapshot_id = snapshot.finish()
        profile.workload.update(
            snapshot_rows=snapshot.record_count,
            snapshot_bytes=snapshot.byte_count,
            runtime_rows=row_count,
        )
        logger.info("回测输入规模 run_id=%s workload=%s", run_id, profile.workload)
        completed = {
            **run,
            "snapshot_id": snapshot_id,
            "benchmark": {"symbol": benchmark, "name": INDEX_CATALOG.get(benchmark, benchmark)}
            if benchmark
            else None,
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
                    "benchmark_equity": str(
                        config.initial_cash
                        * benchmark_prices[item.trading_day.isoformat()]
                        / benchmark_base
                    )
                    if benchmark_base
                    else None,
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
            "symbol_performance": performance_rows(
                [
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
                final_prices,
            ),
            "assumptions": {
                "frequency": "daily",
                "strategy_context_protocol": "strategy-library-v2",
                "intraday_quote": "open-close-midpoint-v1 (contains closing information)",
                "warmup_start_day": history_start.isoformat(),
                "history_trading_days": str(history_window),
                "fundamental_snapshot_sha256": hashlib.sha256(
                    json.dumps(generic_records, sort_keys=True, default=str).encode()
                ).hexdigest(),
                "fee_rate": str(config.fee_rate),
                "slippage_rate": str(config.slippage_rate),
                "excluded_delisted_symbols": sorted(excluded),
                "coverage_exempt_suspended_symbols": sorted(
                    symbol
                    for symbol, item in instruments.items()
                    if item.get("status") == "suspended"
                ),
            },
            "strategy_outputs": strategy_outputs,
            "execution": {"stage": "completed", "trading_day": end_day.isoformat()},
        }
        profile.enter("saving")
        report("saving", 98, force=True)
        completed["timing"] = profile.snapshot()
        container.backtests.save(completed, snapshot)
        profile.enter("completed")
        container.backtests.update_status(run_id, {"timing": profile.snapshot()})
    logger.info(
        "回测快照保存完成 run_id=%s days=%d rows=%d elapsed_seconds=%.3f",
        run_id,
        day_count,
        row_count,
        clock.monotonic() - started,
    )
    return {"status": "succeeded", "backtest_id": run_id, "progress": 100}

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time
from time import perf_counter
from typing import Any
from zoneinfo import ZoneInfo

from easy_quant.application.services.strategy_validation import extract_factor_dependencies
from easy_quant.domain.shared.errors import StateConflictError
from easy_quant.infrastructure.persistence.market_data_pages import DailyBarPageCache
from easy_quant.infrastructure.strategy_runtime.runner import SubprocessStrategyRunner

QUICK_TEST_PRIOR_TRADING_DAYS = 5
logger = logging.getLogger(__name__)


def quick_test_start_day(trading_days: set[date], trading_day: date) -> date:
    previous_days = sorted(day for day in trading_days if day < trading_day)
    return (
        previous_days[-min(QUICK_TEST_PRIOR_TRADING_DAYS, len(previous_days))]
        if previous_days
        else trading_day
    )


def _visible_records(rows: list[dict[str, object]], cutoff: datetime) -> list[dict[str, object]]:
    visible = []
    for row in rows:
        raw_available_at = row.get("available_at")
        if not raw_available_at:
            continue
        available_at = datetime.fromisoformat(str(raw_available_at)).astimezone(UTC)
        if available_at <= cutoff:
            visible.append(row)
    return visible


def execute_strategy_tick(
    container: Any, payload: dict[str, Any], *, job_id: str = ""
) -> dict[str, object]:
    started = perf_counter()
    strategy_id = str(payload["strategy_id"])
    version_id = str(payload["strategy_version_id"])
    trading_day = date.fromisoformat(str(payload["trading_day"]))
    definition = container.state.strategies.get_definition(strategy_id)
    if definition is None or definition.owner_id != str(payload["owner_id"]):
        raise StateConflictError("策略不存在或无权运行")
    version = next(
        (
            item
            for item in container.state.strategies.versions(strategy_id)
            if item.id == version_id
        ),
        None,
    )
    if version is None:
        raise StateConflictError("策略版本不存在")

    dependencies = extract_factor_dependencies(version.source_code)
    trading_days = container.market_data.list_trading_days()
    previous_days = sorted(day for day in trading_days if day < trading_day)[
        -QUICK_TEST_PRIOR_TRADING_DAYS:
    ]
    page_cache = DailyBarPageCache(container.market_data)
    bars = page_cache.days([*previous_days, trading_day])
    read_finished = perf_counter()
    logger.info(
        "快测行情已读取 job_id=%s rows=%d pages=%d seconds=%.3f",
        job_id,
        len(bars),
        len(previous_days) + 1,
        read_finished - started,
    )
    if not any(str(row["trading_day"]) == trading_day.isoformat() for row in bars):
        raise StateConflictError(
            "所选交易日没有日线数据",
            {"trading_day": trading_day.isoformat(), "action_url": "/admin/data"},
        )
    generic_records: dict[str, list[dict[str, object]]] = {}
    for dataset in dependencies - {"daily-bars"}:
        rows = container.market_data.list_records(dataset)
        if not rows:
            raise StateConflictError(
                f"策略运行依赖的数据集 {dataset} 尚未同步",
                {"dataset": dataset, "action_url": "/admin/data/acquisitions"},
            )
        generic_records[dataset] = rows

    phases = ("before_market", "on_market", "after_market")
    contexts: list[tuple[dict[str, object], str]] = []
    for phase in phases:
        include_today = phase == "after_market"
        cutoff = datetime.combine(
            trading_day,
            time(23, 59, 59) if include_today else time(9),
            ZoneInfo("Asia/Shanghai"),
        ).astimezone(UTC)
        visible_bars = [
            row
            for row in bars
            if datetime.fromisoformat(str(row["available_at"])).astimezone(UTC) <= cutoff
            and (
                date.fromisoformat(str(row["trading_day"])) < trading_day
                or (include_today and str(row["trading_day"]) == trading_day.isoformat())
            )
        ]
        prices: dict[str, list[float]] = {}
        for row in sorted(visible_bars, key=lambda item: str(item["trading_day"])):
            prices.setdefault(str(row["symbol"]), []).append(float(str(row["close"])))
        today_rows = [row for row in bars if str(row["trading_day"]) == trading_day.isoformat()]
        symbols = sorted(
            {str(row["symbol"]) for row in visible_bars}
            | ({str(row["symbol"]) for row in today_rows} if phase != "before_market" else set())
        )
        records: dict[str, dict[str, list[dict[str, object]]]] = {}
        for dataset, rows in generic_records.items():
            for row in _visible_records(rows, cutoff):
                records.setdefault(dataset, {}).setdefault(str(row.get("symbol", "")), []).append(
                    row
                )
        contexts.append(
            (
                {
                    "universe": symbols,
                    "prices": prices,
                    "market_values": {},
                    "records": records,
                    "positions": {},
                    "trading_day": trading_day.isoformat(),
                    "phase": phase,
                    "current_prices": {
                        str(row["symbol"]): float(str(row["open"])) for row in today_rows
                    }
                    if phase == "on_market"
                    else {},
                },
                phase,
            )
        )

    context_finished = perf_counter()
    results = SubprocessStrategyRunner(timeout_seconds=30).run_many(
        version, dict(payload.get("parameters", {})), contexts
    )
    runtime_finished = perf_counter()
    logger.info(
        "快测阶段完成 job_id=%s context_seconds=%.3f subprocess_seconds=%.3f cache_hits=%d",
        job_id,
        context_finished - read_finished,
        runtime_finished - context_finished,
        page_cache.stats()["hits"],
    )
    phase_results = []
    failed = False
    for phase, result in zip(phases, results, strict=True):
        failed = failed or result.status != "succeeded"
        phase_results.append(
            {
                "phase": phase,
                "status": result.status.value,
                "signals": [
                    {
                        "symbol": signal.symbol,
                        "action": signal.action,
                        "quantity": str(signal.quantity),
                        "reason": signal.reason,
                    }
                    for signal in result.signals
                ],
                "stdout": result.stdout,
                "error": result.error,
            }
        )
    if failed:
        messages = [str(item["error"]) for item in phase_results if item.get("error")]
        raise StateConflictError(
            "策略快速测试失败", {"phase_results": phase_results, "errors": messages}
        )
    return {
        "status": "succeeded",
        "strategy_id": strategy_id,
        "strategy_version_id": version_id,
        "trading_day": trading_day.isoformat(),
        "phase_results": phase_results,
    }

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from easy_quant.application.services.strategy_validation import extract_factor_dependencies
from easy_quant.domain.shared.errors import StateConflictError
from easy_quant.infrastructure.strategy_runtime.runner import SubprocessStrategyRunner


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


def execute_strategy_tick(container: Any, payload: dict[str, Any]) -> dict[str, object]:
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
    bars = container.market_data.list_bars(end_day=trading_day)
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
        visible_bars = [
            row
            for row in bars
            if date.fromisoformat(str(row["trading_day"])) < trading_day
            or (include_today and str(row["trading_day"]) == trading_day.isoformat())
        ]
        prices: dict[str, list[float]] = {}
        for row in sorted(visible_bars, key=lambda item: str(item["trading_day"])):
            prices.setdefault(str(row["symbol"]), []).append(float(str(row["close"])))
        today_rows = [row for row in bars if str(row["trading_day"]) == trading_day.isoformat()]
        symbols = sorted(
            {str(row["symbol"]) for row in visible_bars}
            | ({str(row["symbol"]) for row in today_rows} if phase != "before_market" else set())
        )
        cutoff = datetime.combine(
            trading_day,
            time(23, 59, 59) if include_today else time(9),
            ZoneInfo("Asia/Shanghai"),
        ).astimezone(UTC)
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

    results = SubprocessStrategyRunner(timeout_seconds=30).run_many(
        version, dict(payload.get("parameters", {})), contexts
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

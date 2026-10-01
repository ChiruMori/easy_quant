from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from flask import Blueprint, g, request

from easy_quant.api.dependencies import get_container
from easy_quant.api.middleware.auth import require_user
from easy_quant.api.responses import success
from easy_quant.api.schemas.backtests import BacktestCompareRequest, BacktestCreateRequest
from easy_quant.application.services.audit_runtime import record_audit
from easy_quant.application.services.strategy_validation import extract_factor_dependencies
from easy_quant.domain.backtesting.engine import run_phased_daily_backtest
from easy_quant.domain.backtesting.entities import BacktestConfig
from easy_quant.domain.backtesting.execution import MarketBar
from easy_quant.domain.market_data.calendar import TradingCalendar
from easy_quant.domain.shared.errors import StateConflictError
from easy_quant.infrastructure.core import UuidGenerator
from easy_quant.infrastructure.strategy_runtime.runner import SubprocessStrategyRunner

from .strategies import repository as strategy_repository

blueprint = Blueprint("backtests", __name__, url_prefix="/api/v1/backtests")


@blueprint.post("")
@require_user
def create_backtest():
    payload = BacktestCreateRequest.model_validate(request.get_json() or {})
    definition = next(
        (
            item
            for item in strategy_repository().definitions.values()
            if item.owner_id == g.current_user.id
            and item.current_version_id == payload.strategy_version_id
        ),
        None,
    )
    if definition is None:
        return success(None, status=404)
    version = next(
        item
        for item in strategy_repository().versions(definition.id)
        if item.id == payload.strategy_version_id
    )
    stored_rows = [
        row for row in get_container().market_data.list_bars(payload.start_day, payload.end_day)
    ]
    dependencies = extract_factor_dependencies(version.source_code)
    generic_missing = [
        dataset
        for dataset in sorted(dependencies - {"daily-bars"})
        if not get_container().market_data.list_records(dataset)
    ]
    if generic_missing:
        raise StateConflictError(
            "策略依赖的数据尚未同步",
            {
                "missing_data": [
                    {
                        "dataset": dataset,
                        "start_day": payload.start_day.isoformat(),
                        "end_day": payload.end_day.isoformat(),
                    }
                    for dataset in generic_missing
                ],
                "recommended_action": "请由管理员在数据管理中同步缺失数据后重试。",
                "action_url": "/admin/data/acquisitions",
            },
        )
    if not stored_rows:
        raise StateConflictError(
            "回测所需行情数据尚未同步",
            {
                "missing_data": [
                    {
                        "dataset": "日线 K 线",
                        "start_day": payload.start_day.isoformat(),
                        "end_day": payload.end_day.isoformat(),
                    }
                ],
                "recommended_action": "请由管理员前往数据管理，先同步策略所需股票及日期范围。",
                "action_url": "/admin/data",
            },
        )
    symbols = sorted({str(row["symbol"]) for row in stored_rows})
    calendar = TradingCalendar(get_container().market_data.list_trading_days() or None)
    expected_days = [
        payload.start_day + timedelta(days=offset)
        for offset in range((payload.end_day - payload.start_day).days + 1)
        if calendar.is_trading_day(payload.start_day + timedelta(days=offset))
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
        if (
            not available_days
            or available_days[0] > expected_start
            or available_days[-1] < expected_end
        ):
            missing.append(
                {
                    "dataset": "日线 K 线",
                    "symbol": symbol,
                    "start_day": expected_start.isoformat(),
                    "end_day": expected_end.isoformat(),
                    "available_start": available_days[0].isoformat() if available_days else None,
                    "available_end": available_days[-1].isoformat() if available_days else None,
                }
            )
    if missing:
        raise StateConflictError(
            "部分策略标的行情覆盖不足，回测已阻止",
            {
                "missing_data": missing,
                "recommended_action": "请按缺失清单同步数据后重新运行，系统不会使用模拟行情补齐。",
                "action_url": "/admin/data",
            },
        )
    config = BacktestConfig(
        payload.strategy_version_id,
        tuple(symbols),
        payload.start_day,
        payload.end_day,
        payload.initial_cash,
        payload.fee_rate,
        payload.slippage_rate,
        payload.benchmark,
        payload.random_seed,
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
        if row["symbol"] in symbols
    ]
    strategy_outputs: list[dict[str, str]] = []
    generic_records = {
        dataset: get_container().market_data.list_records(dataset)
        for dataset in dependencies - {"daily-bars"}
    }

    def strategy_context(trading_day: date, phase: str) -> dict[str, object]:
        visible_rows = [
            row
            for row in stored_rows
            if date.fromisoformat(str(row["trading_day"])) < trading_day
            or (
                phase == "after_market"
                and date.fromisoformat(str(row["trading_day"])) == trading_day
            )
        ]
        prices: dict[str, list[float]] = {}
        for row in sorted(visible_rows, key=lambda item: str(item["trading_day"])):
            prices.setdefault(str(row["symbol"]), []).append(float(str(row["close"])))
        current_prices = (
            {
                str(row["symbol"]): float(str(row["open"]))
                for row in stored_rows
                if date.fromisoformat(str(row["trading_day"])) == trading_day
            }
            if phase == "on_market"
            else {}
        )
        from zoneinfo import ZoneInfo

        cutoff = datetime.combine(
            trading_day,
            time(23, 59, 59) if phase == "after_market" else time(9, 0),
            ZoneInfo("Asia/Shanghai"),
        ).astimezone(UTC)
        records: dict[str, dict[str, list[dict[str, object]]]] = {}
        for dataset, dataset_rows in generic_records.items():
            for row in dataset_rows:
                raw_available_at = row.get("available_at")
                if not raw_available_at:
                    continue
                available_at = datetime.fromisoformat(str(raw_available_at)).astimezone(UTC)
                if available_at > cutoff:
                    continue
                records.setdefault(dataset, {}).setdefault(str(row.get("symbol", "")), []).append(
                    row
                )
        return {
            "universe": symbols,
            "prices": prices,
            "market_values": {},
            "trading_day": trading_day.isoformat(),
            "phase": phase,
            "current_prices": current_prices,
            "records": records,
        }

    call_keys = [
        (trading_day, phase)
        for trading_day in sorted({bar.trading_day for bar in bars})
        for phase in ("before_market", "on_market", "after_market")
    ]
    batch_results = SubprocessStrategyRunner().run_many(
        version,
        {},
        [(strategy_context(trading_day, phase), phase) for trading_day, phase in call_keys],
    )
    phase_results = dict(zip(call_keys, batch_results, strict=True))
    for (trading_day, phase), result in phase_results.items():
        if result.status != "succeeded":
            raise StateConflictError(
                "策略运行失败，未创建回测记录",
                {
                    "phase": phase,
                    "trading_day": trading_day.isoformat(),
                    "strategy_error": result.error or "未知错误",
                },
            )
        if result.stdout:
            strategy_outputs.append(
                {"trading_day": trading_day.isoformat(), "phase": phase, "text": result.stdout}
            )

    def run_phase(trading_day: date, phase: str):
        return phase_results[(trading_day, phase)].signals

    periods, trades, metrics = run_phased_daily_backtest(config, bars, run_phase)
    identifier = f"backtest-{UuidGenerator().new()}"
    run = {
        "id": identifier,
        "owner_id": g.current_user.id,
        "strategy_version_id": payload.strategy_version_id,
        "snapshot_id": hashlib.sha256(
            json.dumps(stored_rows, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "application_version": "0.1.0",
        "created_at": get_container().authentication.clock.now().isoformat(),
        "status": "succeeded",
        "progress": 100,
        "config": payload.model_dump(mode="json"),
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
            "fee_rate": str(payload.fee_rate),
            "slippage_rate": str(payload.slippage_rate),
        },
        "strategy_outputs": strategy_outputs,
    }
    get_container().backtests.save(
        run,
        json.dumps(stored_rows, ensure_ascii=False, sort_keys=True).encode("utf-8"),
    )
    record_audit(
        get_container(),
        actor_user_id=g.current_user.id,
        action="create",
        resource_type="backtest",
        resource_id=identifier,
        after={"status": "succeeded", "strategy_version_id": payload.strategy_version_id},
    )
    return success(run, status=201)


@blueprint.get("")
@require_user
def list_backtests():
    rows = list(get_container().backtests.list_for_owner(g.current_user.id))
    return success(sorted(rows, key=lambda item: str(item["id"]), reverse=True))


@blueprint.get("/<run_id>")
@require_user
def get_backtest(run_id: str):
    run = get_container().backtests.get(run_id)
    if run is None or run["owner_id"] != g.current_user.id:
        return success(None, status=404)
    return success(run)


@blueprint.post("/compare")
@require_user
def compare_backtests():
    payload = BacktestCompareRequest.model_validate(request.get_json() or {})
    rows = []
    for run_id in payload.run_ids:
        run = get_container().backtests.get(run_id)
        if run is not None and run["owner_id"] == g.current_user.id:
            rows.append(run)
    return success({"runs": rows})

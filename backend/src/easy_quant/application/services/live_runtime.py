from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from typing import Any

from easy_quant.application.services.notification_runtime import notify_owner
from easy_quant.application.services.recommendation_actions import (
    actual_portfolio,
    audit_row,
)
from easy_quant.application.services.strategy_validation import extract_factor_dependencies
from easy_quant.domain.shared.errors import StateConflictError
from easy_quant.infrastructure.core import UuidGenerator
from easy_quant.infrastructure.strategy_runtime.runner import SubprocessStrategyRunner


def analyze_live_instance(
    container: Any,
    instance_id: str,
    phase: str,
    decision_at: datetime,
    current_prices: dict[str, object] | None = None,
) -> dict[str, object]:
    if phase not in {"before_market", "on_market", "after_market"}:
        raise ValueError("未知策略阶段")
    with container.live_tracking.transaction() as state:
        instance = state.instances.get(instance_id)
        if instance is None or instance.get("status") != "active":
            raise StateConflictError("实盘实例不存在或未运行")
        portfolio = actual_portfolio(state, instance_id)
        instance = {
            **instance,
            "positions": {key: str(value) for key, value in portfolio.positions.items()},
            "cash": str(portfolio.cash),
            "costs": {key: str(value) for key, value in portfolio.costs.items()},
        }
    repository = container.state.strategies
    version = next(
        (
            version
            for definition in repository.definitions.values()
            for version in repository.versions(definition.id)
            if version.id == instance["strategy_version_id"]
        ),
        None,
    )
    if version is None:
        raise StateConflictError("实盘实例引用的策略版本不存在")

    trading_day = decision_at.date()
    stored_rows = container.market_data.list_bars(end_day=trading_day)
    dependencies = extract_factor_dependencies(version.source_code)
    if "daily-bars" in dependencies and not stored_rows:
        raise StateConflictError(
            "实盘分析所需日线尚未同步",
            {"dataset": "daily-bars", "recommended_action": "请先在数据管理中同步行情。"},
        )
    universe = sorted({str(row["symbol"]) for row in stored_rows})
    prices: dict[str, list[float]] = {}
    for row in sorted(stored_rows, key=lambda item: str(item["trading_day"])):
        row_day = date.fromisoformat(str(row["trading_day"]))
        if row_day < trading_day or (phase == "after_market" and row_day == trading_day):
            prices.setdefault(str(row["symbol"]), []).append(float(str(row["close"])))
    cutoff = decision_at.astimezone(UTC)
    records: dict[str, dict[str, list[dict[str, object]]]] = {}
    for dataset in dependencies - {"daily-bars"}:
        dataset_rows = container.market_data.list_records(dataset)
        if not dataset_rows:
            raise StateConflictError(
                f"实盘分析依赖的数据集 {dataset} 尚未同步",
                {"dataset": dataset, "recommended_action": "请先在数据管理中同步或导入数据。"},
            )
        for row in dataset_rows:
            raw_available_at = row.get("available_at")
            if (
                raw_available_at
                and datetime.fromisoformat(str(raw_available_at)).astimezone(UTC) <= cutoff
            ):
                records.setdefault(dataset, {}).setdefault(str(row.get("symbol", "")), []).append(
                    row
                )
    result = SubprocessStrategyRunner(
        container.settings.strategy_timeout_seconds,
        container.settings.strategy_output_limit_bytes,
    ).run(
        version,
        dict(instance.get("parameters", {})),
        {
            "universe": universe,
            "prices": prices,
            "market_values": {},
            "current_prices": current_prices or {},
            "positions": instance.get("positions", {}),
            "cash": instance["cash"],
            "costs": instance["costs"],
            "trading_day": trading_day.isoformat(),
            "phase": phase,
            "records": records,
        },
        phase=phase,
    )
    if result.status != "succeeded":
        raise StateConflictError(
            "实盘策略运行失败", {"phase": phase, "strategy_error": result.error}
        )

    created: list[dict[str, object]] = []
    notifications: list[tuple[str, str, str]] = []
    with container.live_tracking.transaction() as state:
        current_instance = state.instances.get(instance_id)
        if current_instance is None or current_instance.get("status") != "active":
            raise StateConflictError("实盘实例已暂停或终止")
        latest_portfolio = actual_portfolio(state, instance_id)
        instance["positions"] = latest_portfolio.positions
        recommendations = list(state.recommendations.get(instance_id, []))
        if phase != "after_market":
            for signal in result.signals:
                if phase == "on_market" and not _intraday_triggered(
                    signal.action,
                    signal.trigger_price,
                    (current_prices or {}).get(signal.symbol),
                    instance.get("positions", {}).get(signal.symbol, 0),
                ):
                    continue
                business_key = hashlib.sha256(
                    (
                        f"{instance_id}|{version.id}|{trading_day.isoformat()}|"
                        f"{phase}|{signal.symbol}|{signal.action}"
                    ).encode()
                ).hexdigest()
                existing = next(
                    (item for item in recommendations if item["business_key"] == business_key), None
                )
                if existing:
                    continue
                item: dict[str, object] = {
                    "id": f"recommendation-{UuidGenerator().new()}",
                    "live_instance_id": instance_id,
                    "owner_id": instance["owner_id"],
                    "strategy_version_id": version.id,
                    "decision_at": decision_at.isoformat(),
                    "instrument_id": signal.symbol,
                    "signal_key": phase,
                    "action": signal.action,
                    "quantity": str(signal.quantity),
                    "reason": signal.reason,
                    "trigger_price": str(signal.trigger_price) if signal.trigger_price else None,
                    "suggested_price": str(
                        (current_prices or {}).get(signal.symbol)
                        or (prices.get(signal.symbol) or [None])[-1]
                        or ""
                    ),
                    "business_key": business_key,
                    "status": "pending",
                    "version": 0,
                }
                recommendations.append(item)
                created.append(item)
                state.audit.append(
                    audit_row(
                        UuidGenerator(),
                        container.authentication.clock.now(),
                        None,
                        "create",
                        "recommendation",
                        str(item["id"]),
                        {},
                        {"phase": phase, "action": signal.action, "symbol": signal.symbol},
                        trigger_source="worker",
                    )
                )
                notifications.append(
                    (
                        str(item["id"]),
                        "Easy Quant 操作建议",
                        f"{signal.symbol} {signal.action} {signal.quantity}：{signal.reason}",
                    )
                )
        else:
            today_items = [
                item
                for item in recommendations
                if str(item.get("decision_at", ""))[:10] == trading_day.isoformat()
            ]
            if today_items:
                notifications.append(
                    (
                        f"{instance_id}:{trading_day.isoformat()}:position-reminder",
                        "Easy Quant 盘后持仓核对",
                        f"今日产生 {len(today_items)} 条操作建议，"
                        "请登录平台确认实际成交并更新持仓。",
                    )
                )
        state.recommendations[instance_id] = recommendations
    for notification_id, title, body in notifications:
        notify_owner(container, str(instance["owner_id"]), notification_id, title, body)
    return {
        "phase": phase,
        "trading_day": trading_day.isoformat(),
        "created": created,
        "stdout": result.stdout,
    }


def _intraday_triggered(
    action: str,
    trigger_price: object,
    current_price: object,
    position: object,
) -> bool:
    if trigger_price is None or current_price is None:
        return False
    from decimal import Decimal

    trigger = Decimal(str(trigger_price))
    current = Decimal(str(current_price))
    quantity = Decimal(str(position or 0))
    if action == "buy":
        return quantity == 0 and current <= trigger
    if action == "sell":
        return quantity > 0 and current >= trigger
    return False

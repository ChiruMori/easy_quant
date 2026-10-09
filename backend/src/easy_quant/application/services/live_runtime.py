from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from easy_quant.application.services.instrument_eligibility import currently_unavailable_symbols
from easy_quant.application.services.notification_runtime import notify_owner
from easy_quant.application.services.recommendation_actions import (
    actual_portfolio,
    audit_row,
)
from easy_quant.application.services.strategy_validation import (
    extract_factor_dependencies,
    extract_history_trading_days,
)
from easy_quant.domain.market_data.calendar import TradingCalendar
from easy_quant.domain.shared.errors import StateConflictError
from easy_quant.infrastructure.core import UuidGenerator
from easy_quant.infrastructure.persistence.market_data_pages import DailyBarPageCache
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
    _drain_live_notifications(container, instance_id)
    with container.live_tracking.transaction() as state:
        instance = state.instances.get(instance_id)
        if instance is None or instance.get("status") != "active":
            raise StateConflictError("实盘实例不存在或未运行")
        trading_day = decision_at.astimezone(ZoneInfo("Asia/Shanghai")).date()
        if not TradingCalendar(container.market_data.list_trading_days() or None).is_trading_day(
            trading_day
        ):
            return {"phase": phase, "created": [], "skipped": "非交易日"}
        if str(instance.get("completed_phases", {}).get(phase, "")) >= trading_day.isoformat():
            return {"phase": phase, "created": [], "skipped": "该阶段已执行"}
        state_revision = int(instance.get("state_revision", 0))
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

    trading_day = decision_at.astimezone(ZoneInfo("Asia/Shanghai")).date()
    history_days = extract_history_trading_days(version.source_code)
    previous_days = sorted(
        day for day in container.market_data.list_trading_days() if day < trading_day
    )[-history_days:]
    page_cache = DailyBarPageCache(container.market_data)
    dependencies = extract_factor_dependencies(version.source_code)
    cutoff = decision_at.astimezone(UTC)
    excluded = currently_unavailable_symbols(container.market_data)
    universe_symbols: set[str] = set()
    prices: dict[str, list[str]] = {}
    found_bars = False
    for day in (*previous_days, trading_day):
        for row in page_cache.day(day):
            symbol = str(row["symbol"])
            if symbol in excluded:
                continue
            found_bars = True
            row_available_at = datetime.fromisoformat(str(row["available_at"])).astimezone(UTC)
            include_today = day == trading_day and phase == "after_market"
            if row_available_at <= cutoff and (day < trading_day or include_today):
                universe_symbols.add(symbol)
                prices.setdefault(symbol, []).append(str(row["close"]))
            elif day == trading_day and phase == "on_market":
                universe_symbols.add(symbol)
    if "daily-bars" in dependencies and not found_bars:
        raise StateConflictError(
            "实盘分析所需日线尚未同步",
            {"dataset": "daily-bars", "recommended_action": "请先在数据管理中同步行情。"},
        )
    universe = sorted(
        (universe_symbols | set(current_prices or {}) | set(portfolio.positions)) - excluded
    )
    records: dict[str, dict[str, list[dict[str, object]]]] = {}
    for dataset in dependencies - {"daily-bars"}:
        dataset_rows = container.market_data.list_records(dataset)
        if not dataset_rows:
            raise StateConflictError(
                f"实盘分析依赖的数据集 {dataset} 尚未同步",
                {"dataset": dataset, "recommended_action": "请先在数据管理中同步或导入数据。"},
            )
        for row in dataset_rows:
            if str(row.get("symbol", "")) in excluded:
                continue
            raw_available_at = row.get("available_at")
            if (
                raw_available_at
                and datetime.fromisoformat(str(raw_available_at)).astimezone(UTC) <= cutoff
            ):
                records.setdefault(dataset, {}).setdefault(str(row.get("symbol", "")), []).append(
                    row
                )
    quote_cache = dict(current_prices or {})

    def requested_quotes(symbols: list[str]) -> dict[str, object]:
        if set(symbols) & excluded:
            raise StateConflictError("请求了停牌或退市标的报价")
        missing = [symbol for symbol in symbols if symbol not in quote_cache]
        if missing:
            if phase != "on_market" or container.data_sync is None:
                raise StateConflictError("实时价格服务不可用")
            quote_cache.update(container.data_sync.quotes(missing, force=True))
        unavailable = [symbol for symbol in symbols if symbol not in quote_cache]
        if unavailable:
            raise StateConflictError("实时价格缺失", {"symbols": unavailable})
        return {symbol: quote_cache[symbol] for symbol in symbols}

    runner = SubprocessStrategyRunner(
        container.settings.strategy_timeout_seconds,
        container.settings.strategy_output_limit_bytes,
    )
    execute = runner.run_live if phase == "on_market" else runner.run
    result = execute(
        version,
        dict(instance.get("parameters", {})),
        {
            "universe": universe,
            "prices": prices,
            "market_values": {},
            "current_prices": {
                symbol: price
                for symbol, price in (current_prices or {}).items()
                if symbol not in excluded
            },
            "positions": instance.get("positions", {}),
            "cash": instance["cash"],
            "costs": instance["costs"],
            "trading_day": trading_day.isoformat(),
            "phase": phase,
            "decision_at": decision_at.isoformat(),
            "strategy_state": instance.get("strategy_state", {}),
            "records": records,
        },
        phase=phase,
        **({"quotes": requested_quotes} if phase == "on_market" else {}),
    )
    if result.status != "succeeded":
        raise StateConflictError(
            "实盘策略运行失败", {"phase": phase, "strategy_error": result.error}
        )

    if phase == "on_market":
        requested_quotes(
            sorted(
                {
                    signal.symbol
                    for signal in result.signals
                    if signal.symbol not in excluded and signal.quantity > 0
                }
            )
        )
    created: list[dict[str, object]] = []
    notifications: list[tuple[str, str, str]] = []
    with container.live_tracking.transaction() as state:
        current_instance = state.instances.get(instance_id)
        if current_instance is None or current_instance.get("status") != "active":
            raise StateConflictError("实盘实例已暂停或终止")
        if int(current_instance.get("state_revision", 0)) != state_revision:
            raise StateConflictError("策略状态已更新，请重试")
        if (
            str(current_instance.get("completed_phases", {}).get(phase, ""))
            >= trading_day.isoformat()
        ):
            return {"phase": phase, "created": [], "skipped": "该阶段已执行"}
        latest_portfolio = actual_portfolio(state, instance_id)
        instance["positions"] = latest_portfolio.positions
        recommendations = list(state.recommendations.get(instance_id, []))
        if phase != "after_market":
            for signal in result.signals:
                if signal.symbol in excluded or signal.quantity <= 0:
                    continue
                if phase == "on_market" and not _intraday_triggered(
                    signal.action,
                    signal.trigger_price,
                    quote_cache.get(signal.symbol),
                    instance.get("positions", {}).get(signal.symbol, 0),
                    signal.trigger_operator,
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
                    "ratio": str(signal.ratio) if signal.ratio is not None else None,
                    "ratio_basis": str(signal.ratio_basis)
                    if signal.ratio_basis is not None
                    else None,
                    "trigger_operator": signal.trigger_operator,
                    "reason": signal.reason,
                    "trigger_price": str(signal.trigger_price) if signal.trigger_price else None,
                    "suggested_price": str(
                        quote_cache.get(signal.symbol)
                        or signal.reference_price
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
            if today_items and current_instance.get("after_market_enabled", False):
                notifications.append(
                    (
                        f"{instance_id}:{trading_day.isoformat()}:position-reminder",
                        "Easy Quant 盘后持仓核对",
                        f"今日产生 {len(today_items)} 条操作建议，"
                        "请登录平台确认实际成交并更新持仓。",
                    )
                )
        state.recommendations[instance_id] = recommendations
        current_instance["strategy_state"] = result.state
        current_instance["state_revision"] = state_revision + 1
        outbox = dict(current_instance.get("notification_outbox", {}))
        for event_id, title, body in notifications:
            outbox[event_id] = {"title": title, "body": body}
        current_instance["notification_outbox"] = outbox
        current_instance["completed_phases"] = {
            **current_instance.get("completed_phases", {}),
            phase: trading_day.isoformat(),
        }
        state.instances[instance_id] = current_instance
    _drain_live_notifications(container, instance_id)
    return {
        "phase": phase,
        "trading_day": trading_day.isoformat(),
        "created": created,
        "stdout": result.stdout,
    }


def _drain_live_notifications(container: Any, instance_id: str) -> None:
    with container.live_tracking.transaction() as state:
        instance = state.instances.get(instance_id, {})
        outbox = dict(instance.get("notification_outbox", {}))
        owner_id = str(instance.get("owner_id", ""))
    for event_id, message in outbox.items():
        notify_owner(container, owner_id, event_id, str(message["title"]), str(message["body"]))
        with container.live_tracking.transaction() as state:
            current = state.instances.get(instance_id)
            if current is not None:
                pending = dict(current.get("notification_outbox", {}))
                pending.pop(event_id, None)
                current["notification_outbox"] = pending
                state.instances[instance_id] = current


def _intraday_triggered(
    action: str,
    trigger_price: object,
    current_price: object,
    position: object,
    operator: str | None = None,
) -> bool:
    if current_price is None:
        return False
    current = Decimal(str(current_price))
    quantity = Decimal(str(position or 0))
    if not current.is_finite() or current <= 0 or action not in {"buy", "sell"}:
        return False
    if action == "sell" and quantity <= 0:
        return False
    if trigger_price is None:
        return True
    trigger = Decimal(str(trigger_price))
    direction = operator or ("lte" if action == "buy" else "gte")
    return current <= trigger if direction == "lte" else current >= trigger

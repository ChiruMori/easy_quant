from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from easy_quant.application.ports.live_tracking import LiveTrackingState
from easy_quant.application.services.recommendation_actions import actual_portfolio, ledger_entries
from easy_quant.domain.live_tracking.ledger import rebuild_portfolio
from easy_quant.domain.live_tracking.reservations import reservations


def reporting_snapshot(state: LiveTrackingState, instance_id: str) -> LiveTrackingState:
    """在短事务内复制估值输入，行情读取和历史演算不占用记账锁。"""
    return LiveTrackingState(
        {instance_id: deepcopy(state.instances[instance_id])},
        {instance_id: deepcopy(state.recommendations.get(instance_id, []))},
        {},
        [dict(row) for row in state.ledger if row["live_instance_id"] == instance_id],
        [],
    )


def operation_page(
    state,
    instance_id: str,
    page: int,
    page_size: int,
    search: str = "",
    status: str = "",
    operation_type: str = "",
):
    actual = {
        row["recommendation_id"]: row
        for row in state.operations.values()
        if row.get("recommendation_id") and row.get("kind") in {"confirm", "correct"}
    }
    rows = [
        {
            **row,
            "operation_type": "buy_signal" if row["action"] == "buy" else "sell_signal",
            "actual_quantity": actual.get(row["id"], {}).get("quantity"),
            "actual_price": actual.get(row["id"], {}).get("price"),
            "actual_fee": actual.get(row["id"], {}).get("fee"),
        }
        for row in state.recommendations.get(instance_id, [])
    ]
    rows += [
        {
            **row,
            "instrument_id": row["symbol"],
            "suggested_price": row["price"],
            "decision_at": row["occurred_at"],
            "operation_type": "manual_buy" if row["action"] == "buy" else "manual_sell",
            "status": "executed",
            "version": 0,
            "reason": "用户手动录入",
        }
        for row in state.operations.values()
        if row.get("live_instance_id") == instance_id and row.get("kind") == "manual"
    ]
    if status:
        accepted = {"confirmed", "corrected", "executed"} if status == "executed" else {status}
        rows = [row for row in rows if row["status"] in accepted]
    if operation_type:
        rows = [row for row in rows if row["operation_type"] == operation_type]
    needle = search.strip().casefold()
    if needle:
        rows = [
            row
            for row in rows
            if needle
            in " ".join(
                str(row.get(key, "")) for key in ("instrument_id", "reason", "decision_at")
            ).casefold()
        ]
    fields = {
        "id",
        "instrument_id",
        "action",
        "quantity",
        "suggested_price",
        "suggested_fee",
        "decision_at",
        "reason",
        "status",
        "version",
        "operation_type",
        "ratio",
        "ratio_basis",
        "actual_quantity",
        "actual_price",
        "actual_fee",
    }
    rows = [{key: value for key, value in row.items() if key in fields} for row in rows]
    rows.sort(key=lambda row: (str(row.get("decision_at", "")), str(row["id"])), reverse=True)
    total = len(rows)
    page = min(page, max(1, (total + page_size - 1) // page_size))
    return {
        "items": rows[(page - 1) * page_size : page * page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def portfolio_summary(state, instance_id: str, market_data: Any, now: datetime):
    instance = state.instances[instance_id]
    portfolio = actual_portfolio(state, instance_id)
    entries = ledger_entries(state, instance_id)
    locked = reservations(state.recommendations.get(instance_id, []))
    initial_cash = Decimal(str(instance.get("initial_cash", "100000")))
    initial_positions = {
        key: Decimal(str(value)) for key, value in instance.get("initial_positions", {}).items()
    }
    started = (
        datetime.fromisoformat(str(instance["started_at"]))
        if instance.get("started_at")
        else min((row.occurred_at for row in entries), default=now)
    )
    symbols = set(initial_positions) | {row.symbol for row in entries if row.symbol}
    bars = []
    for symbol in sorted(symbols):
        bars.extend(market_data.list_bars(started.date() - timedelta(days=45), now.date(), symbol))
    bars = sorted(
        [
            row
            for row in bars
            if row.get("available_at") and datetime.fromisoformat(str(row["available_at"])) <= now
        ],
        key=lambda row: (str(row["trading_day"]), str(row["available_at"])),
    )

    def marks(at):
        prices = {}
        for row in bars:
            if datetime.fromisoformat(str(row["available_at"])) <= at:
                price = Decimal(str(row["close"]))
                if price.is_finite() and price > 0:
                    prices[str(row["symbol"])] = price
        return prices

    baseline_prices = marks(started)
    baseline_missing = [
        key for key, value in initial_positions.items() if value and key not in baseline_prices
    ]
    baseline = initial_cash + sum(
        (value * baseline_prices.get(key, Decimal(0)) for key, value in initial_positions.items()),
        Decimal(0),
    )

    def point(at):
        relevant = [row for row in entries if row.occurred_at <= at]
        actual = rebuild_portfolio(initial_cash, relevant, initial_positions)
        prices = marks(at)
        missing = [key for key, value in actual.positions.items() if value and key not in prices]
        added = sum((row.cash_delta for row in relevant if row.symbol is None), Decimal(0))
        equity = actual.cash + sum(
            (value * prices.get(key, Decimal(0)) for key, value in actual.positions.items()),
            Decimal(0),
        )
        valid = not missing and not baseline_missing
        profit = equity - baseline - added
        capital = baseline + added
        return {
            "at": at.isoformat(),
            "equity": str(equity) if valid else None,
            "profit": str(profit) if valid else None,
            "return_rate": str(profit / capital) if valid and capital > 0 else None,
            "missing_symbols": sorted(set(missing + baseline_missing)),
        }

    # 每个已发布行情日保留一个收盘点，并补启动及当前点。
    zone = ZoneInfo("Asia/Shanghai")
    times = {started, now}
    for row in bars:
        at = datetime.fromisoformat(str(row["available_at"]))
        if started < at < now:
            times.add(at.astimezone(zone).replace(hour=23, minute=59, second=59, microsecond=0))
    curve = [point(at) for at in sorted(times) if at <= now]
    current = point(now)
    return {
        **current,
        "cash": str(portfolio.cash),
        "available_cash": str(max(Decimal(0), portfolio.cash - locked.cash)),
        "reserved_cash": str(locked.cash),
        "positions": {key: str(value) for key, value in portfolio.positions.items()},
        "reserved_positions": {key: str(value) for key, value in locked.positions.items()},
        "capital_pool": str(initial_cash + Decimal(str(instance.get("capital_added", 0)))),
        "initial_equity": str(baseline) if not baseline_missing else None,
        "curve": curve,
        "valuation_note": (
            "按已发布日线收盘价估值；收益扣除追加资金，收益率=累计收益/累计投入资金。"
            "初始持仓缺启动时估值或当前持仓缺行情时暂不计算。"
        ),
    }

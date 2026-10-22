from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from easy_quant.application.services.live_reporting import portfolio_summary, reporting_snapshot
from easy_quant.domain.market_data.indices import INDEX_CATALOG, index_instruments
from easy_quant.domain.shared.errors import NotFoundError, StateConflictError, ValidationError

ZONE = ZoneInfo("Asia/Shanghai")


def owned_backtest(container, identifier: str, owner_id: str):
    run = container.backtests.get(identifier)
    if run is None or run["owner_id"] != owner_id:
        raise NotFoundError("backtest")
    return run


def comparison_identity(run):
    config = run.get("config", {})
    if not all(config.get(key) is not None for key in ("start_day", "end_day", "initial_cash")):
        return None
    return (
        str(config["start_day"]),
        str(config["end_day"]),
        Decimal(str(config["initial_cash"])),
        {
            key: Decimal(str(value))
            for key, value in config.get("initial_positions", {}).items()
            if Decimal(str(value)) != 0
        },
    )


def comparison_candidates(container, identifier: str, owner_id: str, search: str):
    current = owned_backtest(container, identifier, owner_id)
    identity = comparison_identity(current)
    if identity is None:
        return []
    return [
        {"id": run["id"], "name": f"{run['id']} · {run.get('created_at', '未记录时间')}"}
        for run in container.backtests.list_for_owner(owner_id)
        if run["id"] != identifier
        and run.get("status") == "succeeded"
        and comparison_identity(run) == identity
        and search.casefold()
        in " ".join(
            str(run.get(key, "")) for key in ("id", "strategy_version_id", "created_at")
        ).casefold()
    ][:20]


def search_instruments(container, search: str):
    rows = {
        str(row["symbol"]): row
        for row in [*index_instruments(), *container.market_data.list_instruments()]
    }
    needle = search.strip().casefold()
    return [
        {"id": symbol, "name": str(row.get("name") or INDEX_CATALOG.get(symbol) or symbol)}
        for symbol, row in sorted(rows.items())
        if needle in f"{symbol} {row.get('name') or INDEX_CATALOG.get(symbol, '')}".casefold()
    ][:20]


def comparison_series(
    container,
    kind: str,
    identifier: str,
    owner_id: str,
    *,
    symbol: str = "",
    other_run_id: str = "",
):
    if bool(symbol) == bool(other_run_id):
        raise ValidationError("请选择一个指数、股票或可比较回测")
    now = container.authentication.clock.now()
    if kind == "backtest":
        run = owned_backtest(container, identifier, owner_id)
        if run.get("status") != "succeeded" or not run.get("periods"):
            raise StateConflictError("请等待回测完成后添加比较")
        identity = comparison_identity(run)
        if identity is None:
            raise StateConflictError("此历史回测缺少完整比较配置")
        base = identity[2]
        if not base.is_finite() or base <= 0:
            raise StateConflictError("没有可比较的初始权益")
        points = [
            (
                str(point["trading_day"]),
                datetime.combine(date.fromisoformat(str(point["trading_day"])), time.max, ZONE),
            )
            for point in run["periods"]
        ]
        baseline_at = points[0][1]
        if other_run_id:
            other = owned_backtest(container, other_run_id, owner_id)
            if (
                other_run_id == identifier
                or other.get("status") != "succeeded"
                or comparison_identity(other) != identity
                or not other.get("periods")
            ):
                raise StateConflictError("只能比较起止日期、初始资金及持仓相同的已完成回测")
            values = {
                str(row["trading_day"]): Decimal(str(row["equity"]))
                for row in other.get("periods", [])
            }
            return {
                "id": f"backtest:{other_run_id}",
                "name": other_run_id,
                "points": [
                    {
                        "day": day,
                        "amount": str(values[day]) if day in values else None,
                        "return_rate": str(values[day] / base - 1) if day in values else None,
                    }
                    for day, _ in points
                ],
            }
    elif kind == "live":
        if other_run_id:
            raise ValidationError("实盘仅支持添加指数或股票比较")
        with container.live_tracking.transaction() as state:
            instance = state.instances.get(identifier)
            if instance is None or instance["owner_id"] != owner_id:
                raise NotFoundError("live_instance")
            snapshot = reporting_snapshot(state, identifier)
        summary = portfolio_summary(snapshot, identifier, container.market_data, now)
        if summary["initial_equity"] is None:
            raise StateConflictError("缺少启动持仓估值，暂不能归一比较曲线")
        base = Decimal(str(summary["initial_equity"]))
        points = [
            (
                datetime.fromisoformat(point["at"]).astimezone(ZONE).date().isoformat(),
                datetime.fromisoformat(point["at"]),
            )
            for point in summary["curve"]
        ]
        baseline_at = points[0][1]
    else:
        raise NotFoundError("comparison")
    if base <= 0 or not points:
        raise StateConflictError("没有可比较的初始权益")
    if not symbol or other_run_id:
        raise ValidationError("请选择一个指数、股票或可比较回测")
    instrument = container.market_data.get_instrument(symbol)
    if instrument is None and symbol not in INDEX_CATALOG:
        raise NotFoundError("instrument")
    bars = sorted(
        container.market_data.list_bars(
            baseline_at.date() - timedelta(days=45), points[-1][1].date(), symbol
        ),
        key=lambda row: (str(row["trading_day"]), str(row["available_at"])),
    )

    def known_price(at):
        found = [
            row for row in bars if datetime.fromisoformat(str(row["available_at"])) <= min(at, now)
        ]
        if not found:
            return None
        price = Decimal(str(found[-1]["close"]))
        return price if price.is_finite() and price > 0 else None

    baseline = known_price(baseline_at)
    if baseline is None:
        raise StateConflictError("比较标的缺少区间起点可获知的真实行情，请先同步数据")
    values = []
    for day, at in points:
        price = known_price(at)
        ratio = price / baseline - 1 if price is not None else None
        values.append(
            {
                "day": day,
                "amount": str(base * (ratio + (1 if kind == "backtest" else 0)))
                if ratio is not None
                else None,
                "return_rate": str(ratio) if ratio is not None else None,
            }
        )
    return {
        "id": f"instrument:{symbol}",
        "name": str((instrument or {}).get("name") or INDEX_CATALOG.get(symbol) or symbol),
        "points": values,
    }

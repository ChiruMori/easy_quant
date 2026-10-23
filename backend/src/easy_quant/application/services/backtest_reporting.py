from __future__ import annotations

from dataclasses import asdict
from datetime import date
from decimal import Decimal

from easy_quant.domain.backtesting.attribution import attribute_trades
from easy_quant.domain.backtesting.entities import SimulatedTrade
from easy_quant.domain.shared.errors import NotFoundError, StateConflictError


def performance_rows(trades, prices):
    return [
        {
            key: str(value) if isinstance(value, Decimal) else value
            for key, value in asdict(row).items()
        }
        for row in attribute_trades(
            [
                SimulatedTrade(
                    date.fromisoformat(row["trading_day"]),
                    row["symbol"],
                    row["action"],
                    Decimal(row["quantity"]),
                    Decimal(row["price"]),
                    Decimal(row["fee"]),
                    Decimal(0),
                )
                for row in trades
            ],
            prices,
        )
    ]


def stock_performance_page(container, identifier, owner_id, page, page_size):
    run = container.backtests.get(identifier)
    if run is None or run["owner_id"] != owner_id:
        raise NotFoundError("backtest")
    if run.get("status") != "succeeded":
        raise StateConflictError("回测完成后可查看股票收益")
    rows = run.get("symbol_performance")
    if rows is None:
        trades = run.get("trades", [])
        prices = (
            container.backtests.snapshot_prices(
                run.get("snapshot_id", ""),
                run["periods"][-1]["trading_day"] if run.get("periods") else "",
                {row["symbol"] for row in trades},
            )
            if trades
            else {}
        )
        rows = performance_rows(trades, prices)
    rows = sorted(
        rows,
        key=lambda row: (
            row["profit"] is None,
            -Decimal(row["profit"] or "0"),
            row["symbol"],
        ),
    )
    return {
        "items": rows[(page - 1) * page_size : page * page_size],
        "total": len(rows),
        "page": page,
        "page_size": page_size,
    }

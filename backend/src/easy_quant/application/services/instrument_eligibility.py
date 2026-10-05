from __future__ import annotations

from typing import Any


def delisted_symbols(market_data: Any) -> set[str]:
    """Return securities explicitly marked as delisted by the catalog."""
    return {
        str(item["symbol"])
        for item in market_data.list_instruments()
        if item.get("status") == "delisted"
    }


def currently_unavailable_symbols(market_data: Any) -> set[str]:
    """Exclude delisted and suspended instruments from current signals."""
    return {
        str(item["symbol"])
        for item in market_data.list_instruments()
        if item.get("status") in {"delisted", "suspended"}
    }

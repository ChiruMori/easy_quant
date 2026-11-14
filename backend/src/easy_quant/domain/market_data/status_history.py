"""状态快照仅在业务状态改变时形成新事件；观测日期不构成状态变化。"""

from datetime import datetime

FIELDS = ("symbol", "name", "exchange", "listed_on", "status", "is_st")


def status_identity(row):
    return tuple(row.get(key) for key in FIELDS)


def same_status(previous, current):
    return status_identity(previous) == status_identity(current) and all(
        key not in current or current[key] == previous.get(key)
        for key in ("suspension_start", "suspension_end", "reason")
    )


def status_changes(rows):
    previous = {}
    result = []
    for row in sorted(
        rows, key=lambda row: (datetime.fromisoformat(row["available_at"]), row["record_key"])
    ):
        symbol = row["symbol"]
        if symbol not in previous or not same_status(previous[symbol], row):
            result.append(row)
            previous[symbol] = row
    return result

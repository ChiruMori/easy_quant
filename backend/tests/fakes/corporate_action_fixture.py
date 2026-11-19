from datetime import UTC, datetime

from easy_quant.application.services.corporate_actions import identity


def event(**changes):
    row = {
        "record_kind": "event",
        "event_id": "000001:2026-09-22",
        "symbol": "000001",
        "ex_date": "2026-09-22",
        "record_date": "2026-09-21",
        "available_at": "2026-09-18T12:00:00+08:00",
        "status": "implemented",
        "kinds": ["cash_dividend"],
        "cash_per_share": "1",
        "share_multiplier": "1",
        "rights_ratio": "0",
        "rights_price": "0",
        "previous_close": "10",
        "cash_pay_date": "2026-09-24",
        "shares_listing_date": None,
        "source": "offline-fixture",
        "evidence": "fixture:announcement-v1",
        **changes,
    }
    row["record_key"] = identity(row)
    return row


def coverage(*events):
    return {
        "record_kind": "coverage",
        "symbol": "000001",
        "start_day": "2026-01-01",
        "end_day": "2026-12-31",
        "complete": True,
        "event_keys": [row["record_key"] for row in events],
        "evidence": "fixture:complete-events",
        "available_at": "2026-10-01T00:00:00+00:00",
        "record_key": "fixture-coverage",
    }


def bar(day="2026-09-21", price="10"):
    return {
        "symbol": "000001",
        "trading_day": day,
        "open": price,
        "high": price,
        "low": price,
        "close": price,
        "volume": "1000",
        "amount": "10000",
        "adjustment": "none",
        "source": "fixture",
        "available_at": f"{day}T15:00:00+08:00",
    }


AS_OF = datetime(2026, 9, 25, tzinfo=UTC)

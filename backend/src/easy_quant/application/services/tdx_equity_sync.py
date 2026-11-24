"""针对已发布通达信价格事件补齐权益，不让补充源覆盖研究价格。"""

from datetime import datetime, time, timedelta
from decimal import Decimal

from easy_quant.application.services.corporate_actions import identity
from easy_quant.domain.market_data.corporate_actions import (
    DATASET,
    ZONE,
    CorporateAction,
    day,
    instant,
    number,
)
from easy_quant.domain.market_data.research_actions import TDX_PRICE_DATASET


def source_day(value):
    return str(value).split("T")[0] if value not in (None, "", "NaT") else None


def enrich_tdx_equity(store, source, symbol: str, observed_at: datetime, *, refresh=False):
    publications = store.list_records(TDX_PRICE_DATASET, symbol)
    if not publications:
        return {"symbol": symbol, "added": 0, "missing": []}
    publication = publications[0]
    events = publication["events"]
    existing = store.list_records(DATASET, symbol)
    bound = {row.get("tdx_price_key") for row in existing if row.get("record_kind") == "event"}
    wanted = [event for event in events if refresh or event["record_key"] not in bound]
    if not wanted:
        return {"symbol": symbol, "added": 0, "missing": []}
    rows = source.fetch(symbol)
    added, missing, invalidated = [], [], []
    for price in wanted:
        matches = [row for row in rows if source_day(row.get("除权日")) == price["ex_date"]]
        try:
            if price["category"] != 1 or number(price["rights_ratio"]):
                raise ValueError("配股/重整/拆合股需要专用权益处置规则")
            if len(matches) != 1:
                raise ValueError("补充来源没有唯一匹配的实施事件")
            supplied = matches[0]
            announced = source_day(supplied.get("实施方案公告日期"))
            record = source_day(supplied.get("股权登记日"))
            if not announced or not record:
                raise ValueError("缺少实施公告或登记日")
            if day(announced) > observed_at.astimezone(ZONE).date():
                raise ValueError("实施公告日期晚于实际观测日期")
            known_at = min(
                datetime.combine(day(announced), time(23, 59, 59), ZONE), instant(observed_at)
            )
            if number(price["cash_per_share"]) and supplied.get("派息比例") is None:
                raise ValueError("通达信存在派息分量，但补充源实际派息金额缺失")
            cash = number(supplied.get("派息比例") or 0) / 10
            shares = (
                1
                + (number(supplied.get("送股比例") or 0) + number(supplied.get("转增比例") or 0))
                / 10
            )
            if abs(shares - number(price["share_multiplier"])) > Decimal("0.000001"):
                raise ValueError("实际送转比例与通达信价格事件不匹配")
            # 日期来自明确来源，不按除权日猜测到账；实际现金可与差异化除权分量不同。
            row = {
                "record_kind": "event",
                "event_id": price["event_id"],
                "symbol": symbol,
                "ex_date": price["ex_date"],
                "record_date": record,
                "cash_per_share": str(cash),
                "share_multiplier": str(shares),
                "rights_ratio": "0",
                "rights_price": "0",
                "previous_close": price["previous_close"],
                "reference_price": price["reference_price"],
                "cash_pay_date": source_day(supplied.get("派息日")),
                "shares_listing_date": source_day(supplied.get("股份到账日"))
                if shares != 1
                else None,
                "kinds": (["cash_dividend"] if cash else [])
                + (["capitalization"] if shares != 1 else []),
                "status": "implemented",
                "source": "cninfo-public-supplement",
                "evidence": f"https://webapi.cninfo.com.cn/#/company?companyid={symbol}",
                "source_payload": supplied,
                "tdx_price_key": price["record_key"],
                "available_at": known_at.isoformat(),
                "availability_basis": "observed"
                if day(announced) == observed_at.astimezone(ZONE).date()
                else "announcement-date-end-reconstruction",
                "observed_at": observed_at.isoformat(),
            }
            if shares != 1:
                listing = row["shares_listing_date"]
                if not listing or listing not in publication.get("share_listing_days", []):
                    raise ValueError("股份到账日期尚无通达信送配股上市记录佐证可卖日期")
            action = CorporateAction.parse(row)
            if action.available_at > instant(observed_at):
                raise ValueError("实施公告尚未到可获知时点")
            prior = [r for r in existing if r.get("event_id") == price["event_id"]]
            if prior:
                latest = max(prior, key=lambda item: instant(item["available_at"]))
                semantic_fields = (
                    "tdx_price_key",
                    "record_date",
                    "cash_per_share",
                    "share_multiplier",
                    "cash_pay_date",
                    "shares_listing_date",
                    "source_payload",
                )
                if all(latest.get(key) == row.get(key) for key in semantic_fields):
                    continue
                row["available_at"] = observed_at.isoformat()
                row["availability_basis"] = "observed-revision"
            row["record_key"] = identity(
                {key: value for key, value in row.items() if key != "observed_at"}
            )
            added.append(row)
        except (ValueError, KeyError, ArithmeticError) as error:
            missing.append({"event_id": price["event_id"], "reason": str(error)})
            if len(matches) == 1 and price["record_key"] in bound:
                invalidated.append(price["event_id"])
    if added:
        store.upsert_records(DATASET, added, count_overwritten=False)
    store.upsert_records(
        "tdx-equity-checks",
        [
            {
                "record_key": symbol,
                "record_kind": "tdx_equity_check",
                "symbol": symbol,
                "available_at": observed_at.isoformat(),
                "checked_at": observed_at.isoformat(),
                "price_keys": sorted(event["record_key"] for event in events),
                "missing": missing,
                "invalidated_event_ids": invalidated,
            }
        ],
        count_overwritten=False,
    )
    return {"symbol": symbol, "added": len(added), "missing": missing}


def enrichment_due(store, publication, now):
    checks = store.list_records("tdx-equity-checks", publication["symbol"])
    if not checks:
        return True
    previous = checks[0]
    if previous.get("price_keys") != sorted(event["record_key"] for event in publication["events"]):
        return True
    recent = any(
        abs((day(event["ex_date"]) - now.astimezone(ZONE).date()).days) <= 14
        for event in publication["events"]
    )
    interval = 1 if recent else 7 if previous.get("missing") else 90
    return now - instant(previous["checked_at"]) >= timedelta(days=interval)

"""将完整通达信事件清单转换为价格能力；原始行情与实际权益不被改写。"""

import hashlib
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from zipfile import BadZipFile

from easy_quant.application.services.corporate_actions import identity
from easy_quant.domain.market_data.corporate_actions import ZONE, day, number
from easy_quant.domain.market_data.indices import is_index
from easy_quant.domain.market_data.research_actions import TDX_PRICE_DATASET, TDX_PRICE_VERSION
from easy_quant.infrastructure.imports.tdx_corporate_actions import archive_candidates
from easy_quant.infrastructure.imports.tdx_daily import parse_calendar

NON_PRICE = {2, 3, 5, 6, 7, 8, 9, 10, 12, 13, 14}


def prepare_tdx_prices(
    store,
    payload: bytes,
    observed_at: datetime,
    *,
    symbols=None,
    apply=False,
    force_rebuild=False,
    catalog_checked_at=None,
    progress=lambda _row: None,
):
    candidates = archive_candidates(payload, observed_at)
    if not candidates:
        raise ValueError("GBBQ 没有有效证券记录，拒绝把空清单发布为无事件覆盖")
    archive_identity = hashlib.sha256(payload).hexdigest()
    grouped = defaultdict(list)
    for row in candidates:
        grouped[row["symbol"]].append(row)
    wanted = (
        set(symbols)
        if symbols
        else {
            str(row["symbol"])
            for row in store.list_instruments()
            if not is_index(str(row["symbol"]))
        }
        | set(grouped)
    )
    publications, summaries = [], []
    end = observed_at.astimezone(ZONE).date()
    source_day = None
    snapshot_days = {
        day(row["archive_snapshot_day"]) for row in candidates if row.get("archive_snapshot_day")
    }
    if snapshot_days and (len(snapshot_days) != 1 or max(snapshot_days) > end):
        raise ValueError("GBBQ 归档日期不一致或晚于实际观测日期")
    source_day = min(snapshot_days) if snapshot_days else None
    if catalog_checked_at is not None and (
        catalog_checked_at.tzinfo is None or catalog_checked_at > observed_at
    ):
        raise ValueError("目录检查时间必须为不晚于观测时点的带时区时间")
    basis_day = catalog_checked_at.astimezone(ZONE).date() if catalog_checked_at else source_day
    valid_through = basis_day or end
    if basis_day is not None:
        # 最新目录含下一交易日预告，按同包官方日历限定盘前有效期。
        # 无日历或年份未知时不猜测；检查时间来自真正的下载回调。
        try:
            calendar = parse_calendar(payload)
        except (ValueError, KeyError, UnicodeError, BadZipFile):
            calendar = None
        if calendar is not None:
            following = basis_day + timedelta(days=1)
            while following.year in calendar.years and calendar.closed(following):
                following += timedelta(days=1)
            if following.year in calendar.years:
                valid_through = following
        end = min(end, valid_through)
    bounds = store.bar_bounds()
    previous_publications = {row["symbol"]: row for row in store.list_records(TDX_PRICE_DATASET)}
    if apply and any(
        day(row["end_day"]) > end
        for symbol, row in previous_publications.items()
        if symbol in wanted
    ):
        raise ValueError("GBBQ 归档早于当前价格发布，拒绝用旧归档回退生产覆盖")
    ordered = sorted(wanted)
    context_cache = {}

    def conversion_key(symbol):
        state = bounds.get(symbol)
        return identity(
            {
                "candidates": sorted(row["record_key"] for row in grouped[symbol]),
                "first_day": str(state["first_day"]) if state else None,
                "version": TDX_PRICE_VERSION,
            }
        )

    def reusable(symbol):
        prior = previous_publications.get(symbol)
        return bool(
            prior
            and not force_rebuild
            and not prior.get("issues")
            and prior.get("conversion_input") == conversion_key(symbol)
            and not any(day(event["ex_date"]) > day(prior["end_day"]) for event in prior["events"])
        )

    for position, symbol in enumerate(ordered):
        state = bounds.get(symbol)
        if state is None:
            summaries.append({"symbol": symbol, "status": "no_raw_history"})
            continue
        input_key = conversion_key(symbol)
        prior = previous_publications.get(symbol)
        if reusable(symbol):
            assert prior is not None
            publication = {
                **prior,
                "end_day": str(end),
                "available_at": observed_at.isoformat(),
                "observed_at": observed_at.isoformat(),
                "archive_identity": archive_identity,
                "archive_snapshot_day": str(source_day) if source_day else None,
                "catalog_valid_through": str(valid_through),
                "catalog_checked_at": catalog_checked_at.isoformat()
                if catalog_checked_at
                else None,
            }
            publication["content_identity"] = identity(
                {key: value for key, value in publication.items() if key != "content_identity"}
            )
            publications.append(publication)
            summaries.append(
                {
                    "symbol": symbol,
                    "status": "reused",
                    "price_events": len(publication["events"]),
                    "issues": [],
                }
            )
            progress(summaries[-1])
            continue
        if symbol not in context_cache:
            selected = [
                key
                for key in ordered[position : position + 100]
                if key in bounds and not reusable(key)
            ]
            context_cache = store.price_event_contexts(
                {
                    key: [
                        day(row["ex_date"])
                        for row in grouped[key]
                        if row["category"] not in NON_PRICE
                    ]
                    for key in selected
                },
                {key: bounds[key]["first_day"] for key in selected},
                end,
            )
        bars = sorted(context_cache.pop(symbol, []), key=lambda row: str(row["trading_day"]))
        if not bars:
            summaries.append({"symbol": symbol, "status": "no_raw_history"})
            continue
        if any(row.get("adjustment") != "none" or not row.get("source") for row in bars) or not any(
            str(row.get("source", "")).startswith("tdx") for row in bars
        ):
            summaries.append({"symbol": symbol, "status": "not_tdx_raw"})
            continue
        start = day(bars[0]["trading_day"])
        days = [str(row["trading_day"]) for row in bars]
        by_day = defaultdict(list)
        for row in grouped[symbol]:
            if row["category"] not in NON_PRICE and day(row["ex_date"]) > start:
                by_day[row["ex_date"]].append(row)
        events, issues = [], []
        for ex_date, rows in sorted(by_day.items()):
            rows = list({row["record_key"]: row for row in rows}.values())
            try:
                if len(rows) != 1:
                    raise ValueError("同日存在多个价格记录，需核对合并语义")
                row = rows[0]
                category = row["category"]
                if category not in {1, 11}:
                    raise ValueError(f"尚不支持的价格调整类别 {category}")
                index = bisect_left(days, ex_date) - 1
                if index < 0:
                    raise ValueError("缺少事件前原始收盘价")
                previous = number(bars[index]["close"])
                c1, c2, c3, c4 = map(number, row["values"])
                cash, shares, rights, price = (
                    (c1 / 10, 1 + c3 / 10, c4 / 10, c2)
                    if category == 1
                    else (Decimal(0), c3, Decimal(0), Decimal(0))
                )
                if (
                    min(cash, rights, price) < 0
                    or min(shares, previous) <= 0
                    or (rights > 0 and price <= 0)
                ):
                    raise ValueError("价格调整数值或每股单位无效")
                reference = (previous - cash + rights * price) / (shares + rights)
                if reference <= 0:
                    raise ValueError("除权参考价非正，请核对源记录及单位")
                if cash == rights == 0 and shares == 1:
                    continue
                event = {
                    "event_id": f"{symbol}:{ex_date}",
                    "symbol": symbol,
                    "ex_date": ex_date,
                    "previous_close": str(previous),
                    "reference_price": str(reference),
                    "price_ratio": str(reference / previous),
                    "cash_per_share": str(cash),
                    "share_multiplier": str(shares),
                    "rights_ratio": str(rights),
                    "rights_price": str(price),
                    "category": category,
                    "candidate_key": row["record_key"],
                    "source": "tdx-official-gbbq",
                    "basis": "historical-effective-date-reconstruction",
                }
                # 权益绑定的是源经济条款，不能因除权前收盘价逐日更新而伪装成条款修订。
                event["record_key"] = identity(
                    {"version": TDX_PRICE_VERSION, "candidate_key": row["record_key"]}
                )
                events.append(event)
            except (ValueError, ArithmeticError) as error:
                issues.append(
                    {
                        "ex_date": ex_date,
                        "reason": str(error),
                        "categories": [row["category"] for row in rows],
                    }
                )
        publication = {
            "record_kind": "tdx_price_publication",
            "record_key": symbol,
            "symbol": symbol,
            "source": "tdx-official-gbbq",
            "schema_version": TDX_PRICE_VERSION,
            "start_day": str(start),
            "end_day": str(end),
            "events": events,
            "issues": issues,
            "availability_basis": "historical-effective-date-reconstruction",
            "observed_at": observed_at.isoformat(),
            "available_at": observed_at.isoformat(),
            "archive_identity": archive_identity,
            "archive_snapshot_day": str(source_day) if source_day else None,
            "catalog_valid_through": str(valid_through),
            "catalog_checked_at": catalog_checked_at.isoformat() if catalog_checked_at else None,
            "context_sources": sorted({str(row["source"]) for row in bars}),
            "supplemental_context_rows": sum(
                not str(row["source"]).startswith("tdx") for row in bars
            ),
            "conversion_input": input_key,
            "share_listing_days": sorted(
                {row["ex_date"] for row in grouped[symbol] if row["category"] == 2}
            ),
            "equity_issues": [
                {
                    "ex_date": row["ex_date"],
                    "category": row["category"],
                    "reason": "派发权证不作为普通股票价格调整，持仓权益需专用处理",
                }
                for row in grouped[symbol]
                if row["category"] in {13, 14}
            ],
        }
        publication["content_identity"] = identity(publication)
        publications.append(publication)
        summary = {
            "symbol": symbol,
            "status": "ready" if not issues else "partial",
            "price_events": len(events),
            "issues": issues,
        }
        summaries.append(summary)
        progress(summary)
    if apply:
        # 内容版本先归档，再原子切换当前全市场。中断最多留下未激活的历史版本。
        history = [
            {**row, "record_key": row["content_identity"]}
            for row in publications
            if previous_publications.get(row["symbol"], {}).get("conversion_input")
            != row["conversion_input"]
            or previous_publications.get(row["symbol"], {}).get("events") != row["events"]
        ]
        if history:
            store.upsert_records("tdx-price-history", history, count_overwritten=False)
        # 全市场一次事务发布；失败保留上一版本，不出现半市场更新。
        store.upsert_records(TDX_PRICE_DATASET, publications, count_overwritten=False)
    return {
        "applied": apply,
        "symbols": len(publications),
        "price_events": sum(len(row["events"]) for row in publications),
        "issue_count": sum(len(row["issues"]) for row in publications),
        "items": summaries,
    }

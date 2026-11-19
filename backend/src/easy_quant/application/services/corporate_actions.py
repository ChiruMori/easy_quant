"""公司行为不可变导入、候选拆解与运行快照边界。"""

import hashlib
import json
from datetime import datetime

from easy_quant.domain.market_data.corporate_actions import (
    DATASET,
    POLICY,
    CorporateAction,
    CorporateActionBook,
    day,
    instant,
)
from easy_quant.domain.shared.errors import ValidationError


def identity(row: dict) -> str:
    return hashlib.sha256(
        json.dumps(row, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def import_manifest(store, document: dict, observed_at: datetime, *, apply: bool = False) -> dict:
    if document.get("schema_version") != POLICY:
        raise ValidationError("公司行为导入协议必须为 corporate-actions-v1")
    source, evidence = document.get("source"), document.get("evidence")
    if not isinstance(source, str) or not source or not isinstance(evidence, str) or not evidence:
        raise ValidationError("必须提供来源和可复核的公开证据身份")
    events, coverage = document.get("events"), document.get("coverage")
    if (
        not isinstance(events, list)
        or not isinstance(coverage, list)
        or len(events) + len(coverage) > 10000
    ):
        raise ValidationError("事件和覆盖必须为清单，单次最多10000条")
    rows = []
    for supplied in events:
        row = {
            key: value
            for key, value in supplied.items()
            if key not in {"record_key", "observed_at"}
        }
        row.update(record_kind="event", source=source, schema_version=POLICY)
        try:
            action = CorporateAction.parse(row)
            if row.get("status") not in {"implemented", "cancelled"}:
                raise ValueError("只能导入已实施事件或明确取消的版本")
            if action.event_id != f"{action.symbol}:{action.ex_date}":
                raise ValueError("event_id必须为证券代码:除权日，同日行为须合并")
            if action.available_at > instant(observed_at):
                raise ValueError("可获知时间不能晚于采集时间")
            if not supplied.get("evidence"):
                raise ValueError("事件必须附原始公告/归档的可核验证据")
        except (ValueError, KeyError, TypeError, ArithmeticError) as error:
            raise ValidationError(f"公司行为导入无效：{error}") from error
        row["record_key"] = identity(row)
        row["observed_at"] = observed_at.isoformat()
        rows.append(row)
    symbols = sorted(
        {str(row["symbol"]) for row in rows} | {str(row["symbol"]) for row in coverage}
    )
    existing = [row for symbol in symbols for row in store.list_records(DATASET, symbol)]
    book = CorporateActionBook([*existing, *rows])
    for supplied in coverage:
        try:
            start, end = day(supplied["start_day"]), day(supplied["end_day"])
            symbol = str(supplied["symbol"])
            if (
                start > end
                or end > observed_at.date()
                or supplied.get("complete") is not True
                or not supplied.get("evidence")
            ):
                raise ValueError("覆盖证明必须完整且带证据，不能用空响应证明没有事件")
            selected = book.events(symbol, instant(observed_at))
            expected = sorted(
                {
                    str(row["record_key"])
                    for row in [*existing, *rows]
                    if row.get("record_kind") == "event"
                    and row.get("symbol") == symbol
                    and start <= day(row["ex_date"]) <= end
                }
            )
            if sorted(supplied.get("event_keys", [])) != expected:
                raise ValueError("覆盖证明必须逐项列明区间内事件的内容身份")
            known_days = {str(event.ex_date) for event in selected}
            if any(
                row.get("record_kind") == "candidate"
                and row.get("symbol") == symbol
                and row.get("price_event_candidate") is not False
                and start <= day(row["ex_date"]) <= end
                and str(row["ex_date"]) not in known_days
                and not str(
                    supplied.get("candidate_resolutions", {}).get(row["record_key"], "")
                ).startswith("dismissed:")
                for row in existing
            ):
                raise ValueError("候选须匹配实施事件，或附dismissed:公开证据说明其不构成除权")
            required_candidates = {
                row["record_key"]
                for row in existing
                if row.get("record_kind") == "candidate"
                and row.get("price_event_candidate") is not False
                and row.get("symbol") == symbol
                and start <= day(row["ex_date"]) <= end
            }
            if set(supplied.get("resolved_candidate_keys", [])) != required_candidates:
                raise ValueError("覆盖证明须列明已核对的全部候选身份")
        except (ValueError, KeyError, TypeError) as error:
            raise ValidationError(f"公司行为覆盖无效：{error}") from error
        row = {
            **supplied,
            "record_kind": "coverage",
            "source": source,
            "schema_version": POLICY,
            "available_at": observed_at.isoformat(),
        }
        row.pop("record_key", None)
        row["record_key"] = identity(
            {key: value for key, value in row.items() if key != "available_at"}
        )
        rows.append(row)
    # 完整验证后才进行一次原子写入；内容寻址 + INSERT IGNORE 保留第一次观测时间。
    if apply:
        store.upsert_records(DATASET, rows)
    return {
        "applied": apply,
        "records": len(rows),
        "symbols": symbols,
        "event_keys": [row["record_key"] for row in rows if row["record_kind"] == "event"],
        "manifest_sha256": identity(document),
    }


def dividend_candidates(rows: list[dict]) -> list[dict]:
    output = []
    for row in rows:
        if not row.get("ex_dividend_date") or not row.get("record_date"):
            continue
        candidate = {
            "schema_version": POLICY,
            "record_kind": "candidate",
            "symbol": row["symbol"],
            "ex_date": row["ex_dividend_date"],
            "record_date": row["record_date"],
            "source": row.get("source", "unknown"),
            "parent_record_key": row.get("record_key"),
            "available_at": row["available_at"],
            "progress": row.get("progress"),
            "cash_per_ten_shares": row.get("cash_per_ten_shares"),
            "bonus_per_ten_shares": row.get("bonus_per_ten_shares"),
            "transfer_per_ten_shares": row.get("transfer_per_ten_shares"),
            "missing": [
                "verified_announcement_version",
                "cash_pay_date",
                "shares_listing_date",
                "complete_event_coverage",
            ],
        }
        candidate["record_key"] = identity(candidate)
        output.append(candidate)
    return output


def runtime_snapshot(store, symbols=None, *, check=lambda: None) -> dict:
    # 完整性证明和晚到记录亦须进入审计快照；经济事件由领域层按时点选择。
    records = []
    for symbol in sorted(set(symbols)) if symbols is not None else [None]:
        check()
        records.extend(
            row
            for row in store.list_records(DATASET, symbol)
            if row.get("price_event_candidate") is not False
        )
        check()
    return {
        "price_policy": POLICY,
        "corporate_actions": records,
        "corporate_actions_sha256": identity(
            {"records": sorted(records, key=lambda row: str(row["record_key"]))}
        ),
    }


def require_raw_bars(rows) -> None:
    for row in rows:
        if row.get("adjustment") != "none" or not row.get("source"):
            from easy_quant.domain.shared.errors import StateConflictError

            raise StateConflictError(
                "运行只接受来源明确的不复权日线，请先审计旧行情", {"symbol": row.get("symbol")}
            )


def decision_snapshot(snapshot: dict, cutoff: datetime) -> dict:
    # 子进程连私有属性也拿不到未来经济版本；完整审计仅由宿主保存。
    records = [
        row
        for row in snapshot["corporate_actions"]
        if row.get("record_kind") == "event" and instant(row["available_at"]) <= cutoff
    ]
    known_keys = {row["record_key"] for row in records}
    records.extend(
        {**row, "event_keys": [key for key in row.get("event_keys", []) if key in known_keys]}
        for row in snapshot["corporate_actions"]
        if row.get("record_kind") == "coverage"
    )
    return {"price_policy": POLICY, "corporate_actions": records}


def validate_research_coverage(snapshot: dict, bars, cutoff: datetime) -> None:
    from easy_quant.domain.market_data.corporate_actions import ZONE

    starts = {}
    end = cutoff.astimezone(ZONE).date()
    for row in bars:
        symbol, trading_day = str(row["symbol"]), day(row["trading_day"])
        if trading_day <= end:
            starts[symbol] = min(starts.get(symbol, trading_day), trading_day)
    book = CorporateActionBook(snapshot["corporate_actions"])
    for symbol, start in starts.items():
        book.require_coverage(symbol, start, end, cutoff)


def sync_tdx_candidates(store, payload: bytes, observed_at: datetime) -> None:
    from easy_quant.infrastructure.imports.tdx_corporate_actions import archive_candidates

    archive_key = hashlib.sha256(payload).hexdigest()
    if any(
        row["record_key"] == archive_key for row in store.list_records("corporate-action-imports")
    ):
        return
    rows = archive_candidates(payload, observed_at)
    store.upsert_records(DATASET, rows, count_overwritten=False)
    # 只有全部候选提交成功才打归档检查点；异常时安全重试且不生成覆盖证明。
    store.upsert_records(
        "corporate-action-imports",
        [
            {
                "record_key": archive_key,
                "symbol": "",
                "source": "tdx-official-gbbq",
                "available_at": observed_at.isoformat(),
                "candidate_count": len(rows),
                "trusted_events_added": 0,
            }
        ],
    )

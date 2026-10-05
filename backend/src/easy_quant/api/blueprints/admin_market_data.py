from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, g, request

from easy_quant.api.dependencies import get_container
from easy_quant.api.middleware.auth import require_admin
from easy_quant.api.responses import success
from easy_quant.api.schemas.market_data import (
    AcquisitionRequest,
    InstrumentStatusRequest,
    SourceOrderRequest,
)
from easy_quant.application.services.audit_runtime import record_audit
from easy_quant.domain.market_data.calendar import TradingCalendar
from easy_quant.domain.scheduling.entities import Job
from easy_quant.domain.shared.errors import ValidationError
from easy_quant.infrastructure.core import UuidGenerator

blueprint = Blueprint("admin_market_data", __name__, url_prefix="/api/v1/admin/market-data")


def _exchange(symbol: str) -> str:
    if symbol.startswith(("4", "8", "92")):
        return "北京证券交易所"
    if symbol.startswith(("5", "6", "9")):
        return "上海证券交易所"
    return "深圳证券交易所"


def _coverage_status(first_day: date | None, last_day: date | None) -> str:
    if first_day is None or last_day is None:
        return "未同步"
    days = (last_day - first_day).days
    if days >= 3652:
        return "完全同步"
    if days >= 1095:
        return "部分同步"
    return "数据不足"


@blueprint.get("/datasets")
@require_admin
def list_datasets():
    return success(list(get_container().state.datasets))


@blueprint.put("/datasets/<dataset_key>/sources")
@require_admin
def update_source_order(dataset_key: str):
    payload = SourceOrderRequest.model_validate(request.get_json() or {})
    dataset = next(
        (item for item in get_container().state.datasets if item["key"] == dataset_key), None
    )
    if dataset is None:
        return success(None, status=404)
    existing = {item["key"]: item for item in dataset["sources"]}
    dataset["sources"] = [existing[key] for key in payload.source_keys if key in existing]
    for source in dataset["sources"]:
        source["enabled"] = source["key"] in payload.enabled_keys
    datasets = get_container().state.datasets
    dataset_index = next(index for index, item in enumerate(datasets) if item["key"] == dataset_key)
    datasets[dataset_index] = dataset
    record_audit(
        get_container(),
        actor_user_id=g.current_user.id,
        action="update",
        resource_type="data-source-config",
        resource_id=dataset_key,
        after={"enabled_sources": sorted(payload.enabled_keys)},
    )
    return success(dataset)


@blueprint.get("/coverage")
@require_admin
def market_data_coverage():
    store = get_container().market_data
    search = request.args.get("search", "").strip()
    sync_status = request.args.get("status", "").strip()
    after_symbol = request.args.get("after", "").strip()
    before_symbol = request.args.get("before", "").strip()
    if after_symbol and before_symbol:
        raise ValidationError("after 和 before 不能同时指定")
    page = max(1, request.args.get("page", 1, type=int) or 1)
    page_size = min(100, max(10, request.args.get("page_size", 50, type=int) or 50))
    instrument_count, total, page, summaries = store.coverage_page(
        page=page,
        page_size=page_size,
        search=search,
        status=sync_status,
        after_symbol=after_symbol,
        before_symbol=before_symbol,
    )
    rows = []
    calendar = TradingCalendar(store.list_trading_days() or None)
    now = get_container().authentication.clock.now()
    for summary in summaries:
        symbol = str(summary["symbol"])
        first_day = summary.get("first_day")
        last_day = summary.get("last_day")
        freshness = calendar.freshness(first_day=first_day, last_day=last_day, now=now)
        delisted = summary.get("status") == "delisted"
        suspended = summary.get("status") == "suspended"
        rows.append(
            {
                "symbol": symbol,
                "name": summary.get("name", ""),
                "exchange": summary.get("exchange", _exchange(symbol)),
                "listed_on": summary.get("listed_on"),
                "status": summary.get("status", "active"),
                "first_trading_day": first_day.isoformat() if first_day else None,
                "last_trading_day": last_day.isoformat() if last_day else None,
                "record_count": summary.get("count", 0),
                "sync_status": "已退市"
                if delisted
                else "已停牌"
                if suspended
                else _coverage_status(first_day, last_day),
                "freshness_status": "delisted"
                if delisted
                else "suspended"
                if suspended
                else freshness.status.value,
                "updated": not (delisted or suspended) and freshness.status.value == "updated",
                "stale": not (delisted or suspended) and freshness.status.value == "stale",
                "previous_trading_day": freshness.previous_trading_day.isoformat(),
                "recommended_end_day": freshness.recommended_end_day.isoformat(),
            }
        )
    return success(
        {
            "instrument_count": instrument_count,
            "total": total,
            "page": page,
            "page_size": page_size,
            "next_cursor": rows[-1]["symbol"] if rows else None,
            "previous_cursor": rows[0]["symbol"] if rows else None,
            "items": rows,
        }
    )


@blueprint.get("/instruments/<symbol>")
@require_admin
def get_instrument(symbol: str):
    normalized = symbol.strip().zfill(6)
    instrument = get_container().market_data.get_instrument(normalized)
    if instrument is None:
        return success(None, status=404)
    return success(instrument)


@blueprint.put("/instruments/<symbol>/status")
@require_admin
def update_instrument_status(symbol: str):
    normalized = symbol.strip().zfill(6)
    payload = InstrumentStatusRequest.model_validate(request.get_json() or {})
    store = get_container().market_data
    existing = store.get_instrument(normalized)
    if existing is None:
        return success(None, status=404)
    if existing.get("status") == "delisted":
        raise ValidationError("已退市股票不能标记为停牌或恢复交易")
    previous_status = existing.get("status")
    if not store.set_instrument_status(normalized, payload.status):
        return success(None, status=404)
    record_audit(
        get_container(),
        actor_user_id=g.current_user.id,
        action="update",
        resource_type="instrument-status",
        resource_id=normalized,
        before={"status": previous_status},
        after={"status": payload.status, "reason": payload.reason},
    )
    return success(store.get_instrument(normalized))


@blueprint.get("/instruments/<symbol>/daily-bars")
@require_admin
def get_instrument_daily_bars(symbol: str):
    normalized = symbol.strip().zfill(6)
    start_day = request.args.get("start_day", type=date.fromisoformat)
    end_day = request.args.get("end_day", type=date.fromisoformat)
    rows = get_container().market_data.list_bars(start_day, end_day, normalized)
    if start_day is None and end_day is None:
        rows = rows[-180:]
    elif len(rows) > 1000:
        rows = rows[-1000:]
    return success(rows)


@blueprint.post("/acquisitions")
@require_admin
def create_acquisition():
    payload = AcquisitionRequest.model_validate(request.get_json() or {})
    tasks = get_container().state.acquisitions
    task = {
        "id": f"task-{UuidGenerator().new()}",
        "dataset_key": payload.dataset_key,
        "force": payload.force,
        "status": "queued",
        "symbols": payload.symbols,
        "start_day": payload.start_day,
        "end_day": payload.end_day,
        "attempts": [],
        "record_count": 0,
    }
    tasks[str(task["id"])] = task
    job_id = f"job-{UuidGenerator().new()}"
    task["job_id"] = job_id
    get_container().jobs.enqueue(
        Job(
            job_id,
            "market-data-acquisition",
            f"market-data:{task['id']}",
            {
                "task_id": task["id"],
                "dataset_key": payload.dataset_key,
                "symbols": payload.symbols,
                "start_day": payload.start_day,
                "end_day": payload.end_day,
                "force": payload.force,
            },
            get_container().authentication.clock.now(),
        )
    )
    record_audit(
        get_container(),
        actor_user_id=g.current_user.id,
        action="execute",
        resource_type="data-acquisition",
        resource_id=str(task["id"]),
        after={"dataset_key": payload.dataset_key, "status": str(task["status"]), "job_id": job_id},
    )
    return success(task, status=202)


@blueprint.get("/acquisitions")
@require_admin
def list_acquisitions():
    return success(list(get_container().state.acquisitions.values()))


@blueprint.get("/acquisitions/<task_id>")
@require_admin
def get_acquisition(task_id: str):
    return success(
        get_container().state.acquisitions.get(task_id, {"id": task_id, "status": "not_found"})
    )


@blueprint.post("/imports/preview")
@require_admin
def preview_import():
    uploaded = request.files.get("file")
    if uploaded is None:
        return success(
            {
                "valid": False,
                "rows": 0,
                "issues": [{"row": 0, "field": "file", "message": "请选择 CSV 文件"}],
            }
        )
    text = uploaded.read().decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    dataset_key = str(request.form.get("dataset_key", "daily-bars"))
    allowed_datasets = {
        "daily-bars",
        "market-values",
        "pledge-ratios",
        "financial-indicators",
        "industry-memberships",
        "security-profiles",
    }
    if dataset_key not in allowed_datasets:
        return success(
            {
                "valid": False,
                "rows": len(rows),
                "issues": [{"row": 0, "field": "dataset_key", "message": "不支持的数据集"}],
            }
        )
    required = (
        {"symbol", "trading_day", "open", "high", "low", "close", "volume"}
        if dataset_key == "daily-bars"
        else {"symbol", "available_at"}
    )
    issues: list[dict[str, object]] = []
    for index, row in enumerate(rows, start=2):
        for field in required:
            if not row.get(field):
                issues.append({"row": index, "field": field, "message": "必填字段不能为空"})
        date_field = "trading_day" if dataset_key == "daily-bars" else "available_at"
        try:
            if dataset_key == "daily-bars":
                date.fromisoformat(row.get(date_field, ""))
            else:
                parsed_at = datetime.fromisoformat(row.get(date_field, ""))
                if parsed_at.tzinfo is None:
                    raise ValueError
        except ValueError:
            issues.append(
                {
                    "row": index,
                    "field": date_field,
                    "message": "日线日期须为 YYYY-MM-DD；其他数据须为带时区的 ISO 时间",
                }
            )
        for field in (
            ("open", "high", "low", "close", "volume") if dataset_key == "daily-bars" else ()
        ):
            try:
                Decimal(row.get(field, ""))
            except InvalidOperation:
                issues.append({"row": index, "field": field, "message": "必须为有效十进制数"})
    preview_id = f"preview-{len(get_container().state.import_previews) + 1}"
    if not issues:
        get_container().state.import_previews[preview_id] = {
            "dataset_key": dataset_key,
            "rows": rows,
        }
    return success(
        {
            "preview_id": preview_id if not issues else None,
            "valid": not issues,
            "rows": len(rows),
            "issues": issues,
        }
    )


@blueprint.post("/imports/commit")
@require_admin
def commit_import():
    payload = request.get_json() or {}
    state = get_container().state
    preview = state.import_previews.pop(str(payload.get("preview_id", "")), None)
    if preview is None:
        return success({"status": "failed", "message": "预检结果不存在或已提交"}, status=409)
    dataset_key = str(preview.get("dataset_key", "daily-bars"))
    rows = preview["rows"]
    if dataset_key != "daily-bars":
        normalized = []
        for row in rows:
            symbol = str(row["symbol"]).zfill(6)
            record_key = str(row.get("record_key") or "")
            if not record_key:
                record_key = hashlib.sha256(
                    json.dumps(row, ensure_ascii=False, sort_keys=True).encode()
                ).hexdigest()
            normalized.append({**row, "symbol": symbol, "record_key": record_key})
        overwritten = get_container().market_data.upsert_records(dataset_key, normalized)
        record_audit(
            get_container(),
            actor_user_id=g.current_user.id,
            action="import",
            resource_type="dataset",
            resource_id=dataset_key,
            after={"rows": len(rows), "overwritten": overwritten},
        )
        return success(
            {"status": "succeeded", "rows": len(rows), "overwritten": overwritten},
            status=201,
        )
    normalized_rows = []
    for row in rows:
        symbol = str(row["symbol"]).zfill(6)
        trading_day = str(row["trading_day"])
        normalized_rows.append(
            {
                "symbol": symbol,
                "trading_day": trading_day,
                "available_at": f"{trading_day}T15:00:00+08:00",
                **{
                    field: str(Decimal(row[field]))
                    for field in ("open", "high", "low", "close", "volume")
                },
            }
        )
    overwritten = get_container().market_data.upsert_bars(normalized_rows)
    existing = {item["symbol"] for item in get_container().market_data.list_instruments()}
    get_container().market_data.upsert_instruments(
        [
            {"symbol": row["symbol"], "name": "", "exchange": _exchange(row["symbol"])}
            for row in normalized_rows
            if row["symbol"] not in existing
        ]
    )
    record_audit(
        get_container(),
        actor_user_id=g.current_user.id,
        action="import",
        resource_type="dataset",
        resource_id="daily-bars",
        after={"rows": len(rows), "overwritten": overwritten},
    )
    return success(
        {"status": "succeeded", "rows": len(rows), "overwritten": overwritten}, status=201
    )

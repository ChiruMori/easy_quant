from datetime import datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from easy_quant.domain.market_data.fundamentals import FIELD_METADATA, report_kind
from easy_quant.infrastructure.data_sources.financial_fields import ALIASES, PROFILE_FIELDS

ZONE = ZoneInfo("Asia/Shanghai")
MISSING = (None, "", "-", "--", "不适用", "N/A")


def number(value: object) -> str | None:
    if value in MISSING:
        return None
    text = str(value).strip().replace(",", "").removesuffix("%")
    try:
        result = Decimal(text)
    except InvalidOperation as error:
        raise ValueError("财务数值格式无效") from error
    if not result.is_finite():
        raise ValueError("财务数值必须有限")
    return str(result)


def source_time(value: object, *, epoch: bool = False) -> str | None:
    if value in MISSING:
        return None
    if epoch:
        at = datetime.fromtimestamp(int(str(value)), ZONE)
    else:
        text = str(value).strip()
        if len(text) == 8 and text.isdigit():
            text = f"{text[:4]}-{text[4:6]}-{text[6:8]}"
        at = datetime.fromisoformat(text)
        if at.tzinfo is None:
            at = at.replace(tzinfo=ZONE)
        # 日期或供应商占位的零点均按当天结束保守可见。
        if at.time() == time(0):
            at = at.replace(hour=23, minute=59, second=59)
    return at.isoformat()


def normalize_financial(dataset: str, symbol: str, row: dict, labels: dict | None = None) -> dict:
    row_symbol = str(row.get("SECURITY_CODE") or row.get("symbol") or symbol).zfill(6)
    if row_symbol != symbol:
        raise ValueError("财务响应股票代码不匹配")
    period_value = row.get("REPORT_DATE") or row.get("report_period") or row.get("END_DATE")
    period_at = source_time(period_value)
    period = period_at[:10] if period_at else ""
    if dataset != "company-profiles" and not period:
        raise ValueError("财务响应缺少报告期")
    published = source_time(
        row.get("NOTICE_DATE") or row.get("published_at") or row.get("HOLD_NOTICE_DATE")
    )
    updated = source_time(row.get("UPDATE_DATE") or row.get("source_updated_at"))
    currency = str(row.get("CURRENCY") or row.get("currency") or "CNY")
    if currency in {"人民币", "RMB"}:
        currency = "CNY"
    output: dict[str, Any] = {
        "schema_version": "financial-v1",
        "symbol": symbol,
        "report_period": period,
        "report_type": report_kind(period),
        "published_at": published,
        "source_updated_at": updated,
        "currency": currency,
        "statement_scope": "合并"
        if str(row.get("statement_scope") or "合并").startswith("合并")
        else str(row["statement_scope"]),
        "period_basis": "时点"
        if dataset in {"balance-sheets", "shareholder-counts"}
        else "年初至报告期累计"
        if dataset in {"income-statements", "cash-flow-statements", "financial-indicators"}
        else "事件/快照",
    }
    if dataset == "company-profiles":
        # 原始概况含电话、邮箱、地址和人员，缓存前即仅投影经营字段。
        safe = {
            target: row[key]
            for key, target in PROFILE_FIELDS.items()
            if row.get(key) not in MISSING
        }
        if not safe.get("company_name"):
            raise ValueError("公司概况缺少公司名称")
        if safe.get("registered_capital") is not None:
            safe["registered_capital"] = str(
                Decimal(number(safe["registered_capital"]) or "0") * 10000
            )
        if safe.get("employee_count") is not None:
            safe["employee_count"] = number(safe["employee_count"])
        output.update(safe)
        output["raw_fields"] = safe.copy()
    else:
        for target, aliases in ALIASES.items():
            raw = next((row[key] for key in aliases if row.get(key) not in MISSING), None)
            output[target] = number(raw)
        if dataset == "business-compositions":
            for field in ("revenue_ratio", "cost_ratio", "profit_ratio"):
                if output[field] is not None:
                    output[field] = str(Decimal(str(output[field])) * 100)
            output["gross_margin"] = number(row.get("GROSS_RPOFIT_RATIO"))
            if output["gross_margin"] is not None:
                output["gross_margin"] = str(Decimal(str(output["gross_margin"])) * 100)
            output.update(item_name=row.get("ITEM_NAME"), category=row.get("MAINOP_TYPE"))
        if dataset == "dividend-plans":
            output.update(
                plan=row.get("IMPL_PLAN_PROFILE"),
                progress=row.get("ASSIGN_PROGRESS"),
                record_date=str(row.get("EQUITY_RECORD_DATE") or "")[:10],
                ex_dividend_date=str(row.get("EX_DIVIDEND_DATE") or "")[:10],
            )
        cleaned = {}
        for key, value in row.items():
            if value in MISSING or isinstance(value, (dict, list)):
                continue
            if isinstance(value, (float, Decimal)):
                value = number(value)
            cleaned[str(key)] = str(value)
        output["raw_fields"] = cleaned
    # 分红预案可以提前公告；其他财报保留来源原值，但不据此倒灌历史。
    if period and published and period > published[:10] and dataset != "dividend-plans":
        output["time_warning"] = f"{symbol} {dataset} {period}：公告早于报告期，按采集时点可见"
    output["field_labels"] = labels or {}
    output["field_units"] = {
        key: item[1] for key, item in FIELD_METADATA.items() if output.get(key) is not None
    }
    return output


def validate_financial_response(request, payload: bytes) -> None:
    import json

    rows = json.loads(payload)
    if not isinstance(rows, list):
        raise ValueError("财务缓存不是记录清单")
    for row in rows:
        if (
            not isinstance(row, dict)
            or row.get("schema_version") != "financial-v1"
            or row.get("symbol") != request.parameters.get("symbol")
        ):
            raise ValueError("财务响应契约或股票不匹配")
        if request.dataset_key != "company-profiles" and not row.get("report_period"):
            raise ValueError("财务响应缺少报告期")
        for key in FIELD_METADATA:
            if row.get(key) is not None:
                number(row[key])

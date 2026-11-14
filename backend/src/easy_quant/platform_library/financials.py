from datetime import datetime

from easy_quant.domain.shared.errors import ValidationError


def visible_versions(rows, period="all"):
    """先由 FactorContext 限制决策时点，再按报告期选择当时可见版本。"""
    if period not in {"all", "annual", "quarterly"}:
        raise ValidationError("报告筛选仅支持 all、annual、quarterly（非年报）")
    selected = {}
    for row in sorted(
        rows,
        key=lambda row: (
            datetime.fromisoformat(str(row["available_at"])),
            row.get("source") == "eastmoney",
            str(row.get("record_key", "")),
        ),
    ):
        report_period = str(row.get("report_period") or "")
        if period == "annual" and not report_period.endswith("12-31"):
            continue
        if period == "quarterly" and report_period.endswith("12-31"):
            continue
        key = (
            report_period or str(row["available_at"]),
            row.get("statement_scope"),
            row.get("category"),
            row.get("item_name"),
            row.get("record_date"),
        )
        selected[key] = dict(row)
    return tuple(
        sorted(
            selected.values(),
            key=lambda row: (
                str(row.get("report_period") or ""),
                datetime.fromisoformat(str(row["available_at"])),
                str(row.get("item_name", "")),
            ),
        )
    )


def financial_history(dataset):
    def read(context, parameters):
        rows = context.read(dataset, str(parameters["symbol"]))
        return visible_versions(rows, str(parameters.get("period", "all")))

    return read

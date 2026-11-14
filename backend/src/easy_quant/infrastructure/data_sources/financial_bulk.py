"""东方财富全市场财务数据，一次只读取一页，游标由聚合任务保存。"""

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from math import ceil
from typing import Any

from easy_quant.infrastructure.data_sources.financial_normalization import normalize_financial

REPORTS = {
    "balance-sheets": "RPT_DMSK_FN_BALANCE",
    "income-statements": "RPT_DMSK_FN_INCOME",
    "cash-flow-statements": "RPT_DMSK_FN_CASHFLOW",
    "financial-indicators": "RPT_F10_FINANCE_MAINFINADATA",
    "company-profiles": "RPT_F10_ORG_BASICINFO",
    "dividend-plans": "RPT_SHAREBONUS_DET",
    "shareholder-counts": "RPT_HOLDERNUM_DET",
}


@dataclass
class BulkPage:
    rows: list
    pages: int
    count: int
    fingerprint: str
    first_code: str
    last_code: str
    failures: list[dict] = field(default_factory=list)

    def __iter__(self) -> Iterator[Any]:
        yield self.rows
        yield self.pages
        yield self.count


class EastMoneyBulkFinancialSource:
    def __init__(self, client):
        self.client = client

    def page(self, dataset, period, page, symbols):
        condition = '(SECURITY_TYPE_CODE in ("058001001","058001008"))'
        if dataset in {"dividend-plans", "shareholder-counts"}:
            condition = ""
        if period:
            field = "END_DATE" if dataset == "shareholder-counts" else "REPORT_DATE"
            condition += f"({field}='{period}')"
        response = self.client.get(
            "https://datacenter.eastmoney.com/securities/api/data/v1/get",
            params={
                "reportName": REPORTS[dataset],
                "columns": "ALL",
                "filter": condition,
                "pageSize": 500,
                "pageNumber": page,
                "sortColumns": "SECURITY_CODE",
                "sortTypes": "1",
                "source": "WEB",
                "client": "WEB",
            },
        )
        response.raise_for_status()
        payload = response.json(parse_float=Decimal)
        result = payload.get("result")
        if payload.get("success") is not True or not isinstance(result, dict):
            raise ValueError("批量财务接口拒绝请求，不能视为空数据")
        count, pages = int(result["count"]), int(result["pages"])
        rows = result.get("data")
        if count == 0 and rows is None:
            rows = []
        if (
            not isinstance(rows, list)
            or pages != ceil(count / 500)
            or len(rows) != min(500, max(0, count - (page - 1) * 500))
        ):
            raise ValueError("批量财务分页数量不完整")
        normalized, identities, failures = [], set(), []
        for row in rows:
            symbol = str(row["SECURITY_CODE"]).zfill(6)
            identity = json.dumps(row, sort_keys=True, default=str)
            if identity in identities:
                raise ValueError("批量财务分页包含重复记录")
            identities.add(identity)
            if symbol not in symbols:
                continue
            try:
                normalized.append(
                    {**normalize_financial(dataset, symbol, row), "source_format": "bulk-v1"}
                )
            except ValueError as error:
                failures.append(
                    {
                        "dataset": dataset,
                        "period": period,
                        "symbol": symbol,
                        "message": f"{dataset} {symbol} {period}：{error}",
                    }
                )
        codes = [str(row["SECURITY_CODE"]).zfill(6) for row in rows]
        if codes != sorted(codes):
            raise ValueError("批量来源未按股票代码稳定排序")
        return BulkPage(
            normalized,
            pages,
            count,
            hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest(),
            codes[0] if codes else "",
            codes[-1] if codes else "",
            failures,
        )

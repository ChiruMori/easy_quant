"""直接访问财报原始接口；网络客户端由组合根注入，适配后再进入来源缓存。"""

import json
from decimal import Decimal
from html.parser import HTMLParser
from math import ceil

import httpx

from easy_quant.domain.market_data.entities import SemanticRequest
from easy_quant.infrastructure.data_sources.financial_normalization import (
    normalize_financial,
    source_time,
)


def market_symbol(symbol: str) -> str:
    if len(symbol) != 6 or not symbol.isdigit():
        raise ValueError("财务数据仅支持六位股票代码")
    return (
        "bj"
        if symbol.startswith(("4", "8", "92"))
        else "sh"
        if symbol.startswith(("5", "6", "9"))
        else "sz"
    ) + symbol


class _CompanyType(HTMLParser):
    value = ""

    def handle_starttag(self, tag, attrs):
        fields = dict(attrs)
        if tag == "input" and fields.get("id") == "hidctype":
            self.value = fields.get("value") or ""


class EastMoneyFinancialSource:
    key = "eastmoney"
    endpoint = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
    reports = {
        "balance-sheets": "zcfzb",
        "income-statements": "lrb",
        "cash-flow-statements": "xjllb",
    }

    def __init__(self, client: httpx.Client):
        self.client = client

    def _json(self, url: str, params: dict) -> dict:
        response = self.client.get(url, params=params)
        response.raise_for_status()
        value = response.json(parse_float=Decimal)
        if not isinstance(value, dict):
            raise ValueError("财务来源响应不是对象")
        return value

    def fetch(self, request: SemanticRequest) -> tuple[bytes, str]:
        symbol = str(request.parameters["symbol"])
        code = market_symbol(symbol)
        dataset = request.dataset_key
        if dataset in self.reports:
            rows = self._statements(code, self.reports[dataset], request.parameters)
        elif dataset == "business-compositions":
            payload = self._json(
                "https://emweb.securities.eastmoney.com/PC_HSF10/BusinessAnalysis/PageAjax",
                {"code": code.upper()},
            )
            rows = payload.get("zygcfx")
            if not isinstance(rows, list):
                raise ValueError("主营构成响应缺少数据清单")
        else:
            report = {
                "financial-indicators": "RPT_F10_FINANCE_MAINFINADATA",
                "company-profiles": "RPT_F10_ORG_BASICINFO",
                "dividend-plans": "RPT_SHAREBONUS_DET",
                "shareholder-counts": "RPT_HOLDERNUM_DET",
            }.get(dataset)
            if report is None:
                raise ValueError("未支持的财务数据集")
            secucode = f"{symbol}.{code[:2].upper()}"
            field = (
                "SECURITY_CODE"
                if dataset in {"dividend-plans", "shareholder-counts"}
                else "SECUCODE"
            )
            rows = self._pages(
                report, f'({field}="{symbol if field == "SECURITY_CODE" else secucode}")', dataset
            )
        normalized = [normalize_financial(dataset, symbol, row) for row in rows]
        return json.dumps(normalized, ensure_ascii=False, default=str).encode(), "application/json"

    def _pages(self, report: str, condition: str, dataset: str) -> list[dict]:
        result_rows = []
        expected = None
        pages = 1
        page = 1
        while page <= pages:
            params = {
                "reportName": report,
                "columns": "ALL",
                "filter": condition,
                "pageSize": 100,
                "pageNumber": page,
                "source": "HSF10",
                "client": "PC",
            }
            url = self.endpoint
            if dataset == "financial-indicators":
                url = "https://datacenter.eastmoney.com/securities/api/data/get"
                params = {
                    "type": report,
                    "sty": "APP_F10_MAINFINADATA",
                    "filter": condition,
                    "p": page,
                    "ps": 100,
                    "sr": -1,
                    "st": "REPORT_DATE",
                    "source": "HSF10",
                    "client": "PC",
                }
            payload = self._json(url, params)
            result = payload.get("result")
            if payload.get("success") is not True or not isinstance(result, dict):
                # 无数据也要求有明确的成功结果，不能把错误伪装成空财报。
                raise ValueError("财务来源拒绝请求或返回无效结果")
            rows = result.get("data")
            total, current_pages = int(result["count"]), int(result["pages"])
            if (
                not isinstance(rows, list)
                or any(not isinstance(row, dict) for row in rows)
                or not 0 <= current_pages <= 100
            ):
                raise ValueError("财务分页结构无效")
            if expected is not None and (expected != total or pages != current_pages):
                raise ValueError("财务分页在采集期间变化")
            expected, pages = total, current_pages
            result_rows.extend(rows)
            page += 1
        if len(result_rows) != expected:
            raise ValueError("财务分页数量不完整")
        identities = {json.dumps(row, sort_keys=True, default=str) for row in result_rows}
        if len(identities) != len(result_rows):
            raise ValueError("财务分页返回重复记录")
        return result_rows

    def _statements(self, code: str, name: str, parameters: dict) -> list[dict]:
        base = "https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis"
        response = self.client.get(f"{base}/Index", params={"type": "web", "code": code})
        response.raise_for_status()
        parser = _CompanyType()
        parser.feed(response.text)
        if not parser.value.isdigit():
            raise ValueError("无法识别财报公司类型")
        params = {"code": code.upper(), "companyType": parser.value, "reportDateType": "0"}
        dates = self._json(f"{base}/{name}DateAjaxNew", params).get("data")
        if not isinstance(dates, list) or len(dates) > 1000:
            raise ValueError("财报日期清单无效")
        wanted = []
        for row in dates:
            day = str(row["REPORT_DATE"])[:10]
            if parameters.get("start_date") and day < str(parameters["start_date"]):
                continue
            if parameters.get("end_date") and day > str(parameters["end_date"]):
                continue
            wanted.append(day)
        if len(set(wanted)) != len(wanted):
            raise ValueError("财报日期清单重复")
        rows = []
        for offset in range(0, len(wanted), 5):
            batch = wanted[offset : offset + 5]
            data = self._json(
                f"{base}/{name}AjaxNew", {**params, "reportType": "1", "dates": ",".join(batch)}
            ).get("data")
            if (
                not isinstance(data, list)
                or len(data) != len(batch)
                or {str(row.get("REPORT_DATE", ""))[:10] for row in data} != set(batch)
            ):
                raise ValueError("财报日期批次返回不完整")
            rows.extend(data)
        return rows


class SinaFinancialSource:
    key = "sina"
    endpoint = (
        "https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022"
    )
    reports = {
        "balance-sheets": "fzb",
        "income-statements": "lrb",
        "cash-flow-statements": "llb",
        "financial-indicators": "gjzb",
    }

    def __init__(self, client: httpx.Client):
        self.client = client

    def fetch(self, request: SemanticRequest) -> tuple[bytes, str]:
        symbol = str(request.parameters["symbol"])
        source = self.reports.get(request.dataset_key)
        if not source:
            raise ValueError("新浪未支持该基本面数据集")
        page = 1
        pages = 1
        expected = None
        records = {}
        while page <= pages:
            response = self.client.get(
                self.endpoint,
                params={
                    "paperCode": market_symbol(symbol),
                    "source": source,
                    "type": 0,
                    "page": page,
                    "num": 100,
                },
            )
            response.raise_for_status()
            payload = response.json(parse_float=Decimal)
            result = payload.get("result", {}).get("data")
            if not isinstance(result, dict) or not isinstance(result.get("report_list"), dict):
                raise ValueError("新浪财报响应无效")
            total = int(result["report_count"])
            if not 0 <= total <= 1000 or (expected is not None and expected != total):
                raise ValueError("新浪财报分页数量无效或变化")
            expected, pages = total, max(1, ceil(total / 100))
            for period, report in result["report_list"].items():
                if period in records:
                    raise ValueError("新浪财报分页重复")
                row = {
                    "report_period": period,
                    "published_at": report.get("publish_date"),
                    "source_updated_at": source_time(report.get("update_time"), epoch=True)
                    if report.get("update_time")
                    else None,
                    "currency": report.get("rCurrency", "CNY"),
                    "statement_scope": report.get("rType", "未知"),
                }
                labels = {}
                fields = report.get("data")
                if not isinstance(fields, list):
                    raise ValueError("新浪报表科目清单无效")
                for item in fields:
                    if item.get("item_value") in (None, "", "--"):
                        continue
                    key = item.get("item_field") or item.get("item_title")
                    # 重复标题/字段仅保留首项，避免相同指标被后续分组覆盖。
                    if key and key not in row:
                        row[key] = item["item_value"]
                        labels[key] = str(item.get("item_title") or key)
                records[period] = normalize_financial(request.dataset_key, symbol, row, labels)
            page += 1
        if len(records) != expected:
            raise ValueError("新浪财报返回不完整")
        return json.dumps(
            list(records.values()), ensure_ascii=False, default=str
        ).encode(), "application/json"

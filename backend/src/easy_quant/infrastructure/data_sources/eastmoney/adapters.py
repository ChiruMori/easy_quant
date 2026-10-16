from __future__ import annotations

import json
from datetime import date, datetime, time
from typing import cast
from zoneinfo import ZoneInfo

from easy_quant.domain.market_data.entities import SemanticRequest
from easy_quant.domain.market_data.indices import is_index
from easy_quant.infrastructure.data_sources.eastmoney.client import EastMoneyClient


class EastMoneySource:
    key = "eastmoney"

    def __init__(self, client: EastMoneyClient) -> None:
        self.client = client

    def fetch(self, request: SemanticRequest) -> tuple[bytes, str]:
        if request.dataset_key == "trading-status":
            return self._suspensions(date.fromisoformat(str(request.parameters["end_day"])))
        parameters = dict(request.parameters)
        path = "api/qt/clist/get"
        if request.dataset_key == "securities":
            parameters = {
                "pn": parameters.get("page", 1),
                "pz": parameters.get("page_size", 10000),
                "po": 1,
                "np": 1,
                "fltt": 2,
                "invt": 2,
                "fid": "f3",
                "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
                "fields": "f12,f14,f26",
            }
        elif request.dataset_key == "daily-bars":
            symbol = str(parameters["symbol"])
            market = (
                ("1" if symbol.startswith("sh") else "0")
                if is_index(symbol)
                else "1"
                if symbol.startswith(("5", "6", "9"))
                else "0"
            )
            path = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
            parameters = {
                "secid": f"{market}.{symbol[2:] if is_index(symbol) else symbol}",
                "klt": 101,
                "lmt": 10000,
                "fqt": 0
                if is_index(symbol) or parameters.get("adjustment", "qfq") == "none"
                else 1,
                "beg": str(parameters["start_date"]).replace("-", ""),
                "end": str(parameters["end_date"]).replace("-", ""),
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            }
        elif request.dataset_key == "live-quotes":
            path = "api/qt/ulist.np/get"
            parameters = {
                "fltt": 2,
                "secids": ",".join(
                    _quote_secid(str(symbol))
                    for symbol in cast(list[str], parameters.get("symbols", []))
                ),
                "fields": "f2,f12,f14",
            }
        elif request.dataset_key == "market-values":
            path = "api/qt/clist/get"
            parameters = {
                "pn": 1,
                "pz": 10000,
                "po": 1,
                "np": 1,
                "fltt": 2,
                "fid": "f3",
                "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
                "fields": "f9,f12,f14,f20,f21,f23",
            }
        else:
            raise ValueError(f"东方财富不支持数据集 {request.dataset_key}")
        data = self.client.get_json(path, parameters)
        return json.dumps(data, ensure_ascii=False, sort_keys=True).encode(), "application/json"

    def _suspensions(self, day: date) -> tuple[bytes, str]:
        """只接受指定交易日的整日停牌证据，预计复牌日不作为恢复依据。"""
        rows: list[dict] = []
        total = None
        pages = 1
        page = 1
        while page <= pages:
            payload = self.client.get_json(
                "https://datacenter-web.eastmoney.com/api/data/v1/get",
                {
                    "reportName": "RPT_CUSTOM_SUSPEND_DATA_INTERFACE",
                    "columns": "ALL",
                    "filter": f"(MARKET=\"全部\")(DATETIME='{day.isoformat()}')",
                    "sortColumns": "SUSPEND_START_DATE",
                    "sortTypes": "-1",
                    "pageSize": 500,
                    "pageNumber": page,
                    "source": "WEB",
                    "client": "WEB",
                },
            )
            result = payload.get("result")
            if payload.get("success") is not True or not isinstance(result, dict):
                raise ValueError("停牌状态来源响应无效，保留原有状态")
            current = result.get("data")
            count = int(result["count"])
            page_count = int(result["pages"])
            if not isinstance(current, list) or not 0 <= page_count <= 100:
                raise ValueError("停牌状态分页无效")
            if total is not None and (count != total or page_count != pages):
                raise ValueError("停牌状态分页发生变化，请重试")
            total, pages = count, page_count
            if any(not isinstance(row, dict) for row in current):
                raise ValueError("停牌状态记录无效")
            rows.extend(current)
            page += 1
        if len(rows) != total:
            raise ValueError("停牌状态清单不完整，保留原有状态")
        normalized = {}
        for row in rows:
            symbol = str(row.get("SECURITY_CODE", ""))
            start = row.get("SUSPEND_START_TIME")
            end = row.get("SUSPEND_END_TIME")
            if len(symbol) != 6 or not symbol.isdigit() or not start:
                raise ValueError("停牌状态缺少股票代码或开始时间")
            start_at = datetime.fromisoformat(str(start))
            end_at = datetime.fromisoformat(str(end)) if end else None
            if start_at.date() > day or (end_at and end_at.date() < day):
                continue
            if start_at.date() == day and start_at.time() > time(9, 30):
                continue
            if end_at and end_at.date() == day and end_at.time() < time(15):
                continue
            if end_at is None and row.get("SUSPEND_EXPIRE") != "连续停牌":
                continue
            normalized[symbol] = {
                "symbol": symbol,
                "status": "suspended",
                "suspension_start": start_at.replace(tzinfo=ZoneInfo("Asia/Shanghai")).isoformat(),
                "suspension_end": end_at.replace(tzinfo=ZoneInfo("Asia/Shanghai")).isoformat()
                if end_at
                else None,
                "as_of_day": day.isoformat(),
            }
        return json.dumps(list(normalized.values()), sort_keys=True).encode(), "application/json"


def diagnose_page(total: int, rows: list[object], page: int, page_size: int) -> dict[str, object]:
    expected = max(0, min(page_size, total - (page - 1) * page_size))
    return {
        "page": page,
        "expected": expected,
        "actual": len(rows),
        "complete": len(rows) == expected,
    }


def _quote_secid(symbol: str) -> str:
    if is_index(symbol):
        return f"{1 if symbol.startswith('sh') else 0}.{symbol[2:]}"
    market = "1" if symbol.startswith(("5", "6", "9")) and not symbol.startswith("92") else "0"
    return f"{market}.{symbol}"

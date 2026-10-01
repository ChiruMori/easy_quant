from __future__ import annotations

import json

from easy_quant.domain.market_data.entities import SemanticRequest
from easy_quant.infrastructure.data_sources.eastmoney.client import EastMoneyClient


class EastMoneySource:
    key = "eastmoney"

    def __init__(self, client: EastMoneyClient) -> None:
        self.client = client

    def fetch(self, request: SemanticRequest) -> tuple[bytes, str]:
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
            market = "1" if symbol.startswith(("5", "6", "9")) else "0"
            path = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
            parameters = {
                "secid": f"{market}.{symbol}",
                "klt": 101,
                "fqt": 1,
                "beg": str(parameters["start_date"]).replace("-", ""),
                "end": str(parameters["end_date"]).replace("-", ""),
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            }
        elif request.dataset_key == "live-quotes":
            path = "api/qt/clist/get"
            parameters = {
                "pn": 1,
                "pz": 10000,
                "po": 1,
                "np": 1,
                "fltt": 2,
                "fid": "f3",
                "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
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


def diagnose_page(total: int, rows: list[object], page: int, page_size: int) -> dict[str, object]:
    expected = max(0, min(page_size, total - (page - 1) * page_size))
    return {
        "page": page,
        "expected": expected,
        "actual": len(rows),
        "complete": len(rows) == expected,
    }

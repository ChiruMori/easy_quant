"""新浪全市场证券与估值直连；每个 HTTP 由注入客户端统一限频。"""

import json
from decimal import Decimal
from math import ceil

BASE = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center."


class SinaMarketSource:
    key = "sina"

    def __init__(self, client):
        self.client = client

    def _get(self, method, params):
        response = self.client.get(BASE + method, params=params)
        response.raise_for_status()
        return response.json(parse_float=Decimal)

    def fetch(self, request):
        if request.dataset_key not in {"securities", "market-values"}:
            raise ValueError("新浪市场来源不支持该数据集")
        count = int(self._get("getHQNodeStockCount", {"node": "hs_a"}))
        if not 1 <= count <= 20000:
            raise ValueError("新浪证券数量无效")
        rows, seen = [], set()
        for page in range(1, ceil(count / 100) + 1):
            batch = self._get(
                "getHQNodeData",
                {
                    "page": page,
                    "num": 100,
                    "sort": "symbol",
                    "asc": 1,
                    "node": "hs_a",
                    "symbol": "",
                    "_s_r_a": "page",
                },
            )
            if not isinstance(batch, list) or len(batch) != min(100, count - len(rows)):
                raise ValueError("新浪证券分页不完整")
            for raw in batch:
                code = str(raw.get("code", ""))
                if len(code) != 6 or not code.isdigit() or code in seen or not raw.get("name"):
                    raise ValueError("新浪证券代码/名称无效或重复")
                seen.add(code)
                item = {"symbol": code, "code": code, "name": raw["name"]}
                if request.dataset_key == "market-values":
                    for target, field, scale in (
                        ("pe_ratio", "per", 1),
                        ("pb_ratio", "pb", 1),
                        ("market_cap", "mktcap", 10000),
                        ("circulating_market_cap", "nmc", 10000),
                    ):
                        value = raw.get(field)
                        if value in (None, "", "--", "-"):
                            item[target] = None
                        else:
                            number = Decimal(str(value)) * scale
                            if not number.is_finite():
                                raise ValueError(f"新浪估值 {code} {field} 非有限数值")
                            item[target] = str(number)
                rows.append(item)
        if int(self._get("getHQNodeStockCount", {"node": "hs_a"})) != count:
            raise ValueError("新浪证券分页期间总数变化，请重试")
        return json.dumps(
            {"data": {"total": count, "diff": rows}}, ensure_ascii=False
        ).encode(), "application/json"

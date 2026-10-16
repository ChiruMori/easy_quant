from __future__ import annotations

import json
from datetime import date
from typing import Any

import httpx

from easy_quant.domain.market_data.entities import SemanticRequest
from easy_quant.domain.market_data.indices import is_index


class TencentDailySource:
    key = "tencent"

    def __init__(self, client: httpx.Client, stock_source: Any):
        self.client, self.stock_source = client, stock_source

    def fetch(self, request: SemanticRequest) -> tuple[bytes, str]:
        symbol = str(request.parameters.get("symbol", "")).lower()
        if not is_index(symbol):
            return self.stock_source.fetch(request)
        start = date.fromisoformat(str(request.parameters["start_date"]))
        end = date.fromisoformat(str(request.parameters["end_date"]))
        rows = {}
        for year in range(start.year, end.year + 1):
            response = self.client.get(
                "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get",
                params={
                    "param": f"{symbol},day,{year}-01-01,{year}-12-31,640,",
                    "_var": "kline_day",
                },
            )
            response.raise_for_status()
            text = response.text
            payload = json.loads(text[text.find("{") :])
            data = payload.get("data", {}).get(symbol, {})
            candles = data.get("day")
            if payload.get("code", 0) != 0 or not isinstance(candles, list):
                raise ValueError("腾讯指数响应缺少不复权日线")
            for row in candles:
                if not isinstance(row, list) or len(row) < 6:
                    raise ValueError("腾讯指数日线字段不完整")
                day = date.fromisoformat(str(row[0]))
                if start <= day <= end:
                    rows[day] = dict(
                        zip(
                            ("date", "open", "close", "high", "low", "volume"), row[:6], strict=True
                        )
                    )
        return json.dumps(
            [rows[day] for day in sorted(rows)], ensure_ascii=False
        ).encode(), "application/json"

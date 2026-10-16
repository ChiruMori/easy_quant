from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

from easy_quant.domain.market_data.entities import SemanticRequest
from easy_quant.domain.market_data.indices import is_index


class AkShareDailySource:
    key = "akshare"

    def __init__(
        self, client: httpx.Client, stocks: Any, decode: Callable[[str], list[dict[str, Any]]]
    ):
        self.client, self.stocks, self.decode = client, stocks, decode

    def fetch(self, request: SemanticRequest) -> tuple[bytes, str]:
        symbol = str(request.parameters.get("symbol", "")).lower()
        if not is_index(symbol):
            return self.stocks.fetch(request)
        response = self.client.get(
            f"https://finance.sina.com.cn/realstock/company/{symbol}/hisdata/klc_kl.js"
        )
        response.raise_for_status()
        encoded = response.text.split("=", 1)[1].split(";", 1)[0].strip().strip('"')
        rows = self.decode(encoded)
        start, end = str(request.parameters["start_date"]), str(request.parameters["end_date"])
        selected = [
            {**row, "date": str(row["date"])[:10]}
            for row in rows
            if start <= str(row["date"])[:10] <= end
        ]
        return json.dumps(selected, default=str).encode(), "application/json"

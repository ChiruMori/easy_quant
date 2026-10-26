from __future__ import annotations

import json
import re
from typing import cast

import httpx

from easy_quant.domain.market_data.entities import SemanticRequest
from easy_quant.domain.market_data.indices import is_index


def quote_symbol(symbol: str) -> str:
    if is_index(symbol):
        return symbol
    if not re.fullmatch(r"\d{6}", symbol):
        raise ValueError("报价标的代码格式无效")
    market = (
        "bj"
        if symbol.startswith(("4", "8", "92"))
        else "sh"
        if symbol.startswith(("5", "6", "9"))
        else "sz"
    )
    return market + symbol


class TencentQuoteSource:
    key = "tencent"

    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def fetch(self, request: SemanticRequest) -> tuple[bytes, str]:
        if request.dataset_key != "live-quotes":
            raise ValueError("腾讯报价来源只支持 live-quotes")
        identifiers = {
            quote_symbol(str(symbol)): str(symbol)
            for symbol in cast(list, request.parameters["symbols"])
        }
        symbols = sorted(identifiers)
        rows = []
        for offset in range(0, len(symbols), 100):
            batch = symbols[offset : offset + 100]
            response = self.client.get("https://qt.gtimg.cn/q=" + ",".join(batch))
            response.raise_for_status()
            text = response.content.decode("gb18030")
            for identifier, record in re.findall(r'v_((?:sh|sz|bj)\d{6})="([^"\r\n]*)"', text):
                if identifier not in batch:
                    continue
                fields = record.split("~")
                if len(fields) < 4 or fields[2] != identifier[2:]:
                    raise ValueError("腾讯实时报价字段不完整或标的身份不一致")
                rows.append({"code": identifiers[identifier], "price": fields[3]})
        return json.dumps(rows, sort_keys=True).encode(), "application/json"

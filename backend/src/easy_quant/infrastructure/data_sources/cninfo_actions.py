"""只补齐通达信缺少的实际权益日期/金额；单次请求在有时限的独立进程中运行。"""

import json
import os
import subprocess
import sys

from easy_quant.infrastructure.data_sources.request_budget import before_data_request

PROGRAM = """
import akshare as ak
import sys
frame = ak.stock_dividend_cninfo(sys.argv[1])
print(frame.to_json(orient='records',date_format='iso',force_ascii=True))
"""


class CninfoEquitySource:
    def fetch(self, symbol: str) -> list[dict]:
        if len(symbol) != 6 or not symbol.isdigit():
            raise ValueError("权益资料只接受六位证券代码")
        before_data_request()
        environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper()
            in {
                "SYSTEMROOT",
                "WINDIR",
                "PATH",
                "TEMP",
                "TMP",
                "USERPROFILE",
                "APPDATA",
                "LOCALAPPDATA",
            }
        }
        try:
            result = subprocess.run(
                [sys.executable, "-I", "-c", PROGRAM, symbol],
                capture_output=True,
                timeout=25,
                env=environment,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("巨潮权益资料请求超时，子进程已终止") from None
        if result.returncode or len(result.stdout) > 2 * 1024 * 1024:
            raise RuntimeError("巨潮权益资料请求失败或响应过大")
        rows = json.loads(result.stdout)
        if not isinstance(rows, list) or len(rows) > 2000:
            raise ValueError("巨潮权益资料格式无效")
        return rows

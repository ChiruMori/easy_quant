from __future__ import annotations

from decimal import Decimal, InvalidOperation


def normalize_live_quotes(value: object, wanted: set[str]) -> dict[str, str]:
    if isinstance(value, dict):
        data = value.get("data")
        rows = data.get("diff", []) if isinstance(data, dict) else []
    else:
        rows = value if isinstance(value, list) else []
    if not isinstance(rows, list):
        raise ValueError("实时报价响应结构无效")
    result: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("f12") or row.get("代码") or row.get("code") or "").zfill(6)
        if symbol not in wanted:
            continue
        raw_price = next((row[key] for key in ("f2", "最新价", "price") if key in row), None)
        try:
            price = Decimal(str(raw_price))
        except InvalidOperation:
            raise ValueError(f"实时价格格式无效：{symbol}") from None
        if not price.is_finite() or price <= 0:
            raise ValueError(f"实时价格必须为有限正数：{symbol}")
        if symbol in result and Decimal(result[symbol]) != price:
            raise ValueError(f"实时报价重复且不一致：{symbol}")
        result[symbol] = str(price)
    missing = wanted - result.keys()
    if missing:
        raise ValueError(f"实时价格缺失：{','.join(sorted(missing)[:20])}")
    return result

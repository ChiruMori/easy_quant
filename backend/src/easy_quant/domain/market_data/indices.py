"""指数与股票使用独立代码空间；指数仅用于分析，不能交易。"""

INDEX_CATALOG = {
    "sh000001": "上证指数",
    "sh000016": "上证50",
    "sh000300": "沪深300",
    "sh000905": "中证500",
    "sh000852": "中证1000",
    "sz399001": "深证成指",
    "sz399006": "创业板指",
}


def is_index(symbol: str) -> bool:
    return len(symbol) == 8 and symbol[:2].lower() in {"sh", "sz"} and symbol[2:].isdigit()


def benchmark_symbol(symbol: str) -> str:
    value = symbol.strip().lower()
    if value in {"000300", "000016", "000905", "000852"}:
        return f"sh{value}"
    if value in {"399001", "399006"}:
        return f"sz{value}"
    return value


def index_instruments() -> list[dict[str, object]]:
    return [
        {
            "symbol": symbol,
            "name": name,
            "exchange": "上海证券交易所" if symbol.startswith("sh") else "深圳证券交易所",
            "status": "active",
        }
        for symbol, name in INDEX_CATALOG.items()
    ]

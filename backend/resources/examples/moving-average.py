def before_market(context, parameters):
    """盘前使用此前已知日线，选择价格站上 5 日均线的股票。"""
    ratio = parameters.get("ratio", "0.10")
    signals = []
    for symbol in context.universe():
        bars = context.factor("market.daily-bars", symbol=symbol)
        ma5 = context.factor("technical.ma", symbol=symbol, window=5)
        if ma5["available"] and bars[-1]["close"] > ma5["value"]:
            signals.append(
                context.signal(symbol, "buy", ratio, "收盘价站上 5 日均线", price=bars[-1]["close"])
            )
    return signals


def on_market(context, parameters):
    """声明盘中触发价；平台每天统一时刻判断一次，不会自动下单。"""
    trigger = parameters.get("intraday_buy_price")
    if trigger is None:
        return []
    signals = []
    for symbol in context.universe():
        if context.position(symbol) == 0:
            signals.append(
                context.signal(
                    symbol,
                    "buy",
                    parameters.get("ratio", "0.10"),
                    "盘中价格到达预设买点",
                    price=trigger,
                    trigger_price=trigger,
                )
            )
    return signals


def after_market(context, parameters):
    """盘后可读取当日收盘数据，本示例只输出运行信息。"""
    return []

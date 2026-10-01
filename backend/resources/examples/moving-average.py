def before_market(context, parameters):
    """盘前选择收盘价站上 5 日均线的股票。"""
    quantity = int(parameters.get("quantity", 100))
    signals = []
    for symbol in context.universe():
        bars = context.factor("market.daily-bars", symbol=symbol)
        ma5 = context.factor("technical.ma", symbol=symbol, window=5)
        if ma5["available"] and bars[-1]["close"] > ma5["value"]:
            signals.append(
                {
                    "symbol": symbol,
                    "action": "buy",
                    "quantity": quantity,
                    "reason": "收盘价站上 5 日均线",
                }
            )
    return signals


def on_market(context, parameters):
    """声明盘中买点；平台命中价格且仓位允许时通知用户。"""
    trigger = parameters.get("intraday_buy_price")
    if trigger is None:
        return []
    return [
        {
            "symbol": symbol,
            "action": "buy",
            "quantity": int(parameters.get("quantity", 100)),
            "trigger_price": trigger,
            "reason": "盘中价格到达预设买点",
        }
        for symbol in context.universe()
        if context.position(symbol) == 0
    ]


def after_market(context, parameters):
    """盘后钩子；实盘有过建议时平台另行提示用户更新仓位。"""
    print("盘后检查完成")
    return []

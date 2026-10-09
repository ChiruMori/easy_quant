def before_market(context, parameters):
    """以市值和历史预期回报筛选候选股票。"""
    ratio = parameters.get("ratio", "0.10")
    signals = []
    for symbol in context.universe():
        value = context.factor("market.value", symbol=symbol)
        expected = context.factor("stat.expected-return", symbol=symbol)
        if value and expected["available"] and expected["expected_return"] > 0:
            bars = context.factor("market.daily-bars", symbol=symbol)
            if bars:
                signals.append(
                    context.signal(symbol, "buy", ratio, "正预期回报候选", price=bars[-1]["close"])
                )
    return signals


def on_market(context, parameters):
    return []


def after_market(context, parameters):
    return []

def before_market(context, parameters):
    """使用平台市值和历史预期回报因子选股。"""
    signals = []
    for symbol in context.universe():
        value = context.factor("market.value", symbol=symbol)
        expected = context.factor("stat.expected-return", symbol=symbol)
        if value and expected["available"] and expected["expected_return"] > 0:
            signals.append(
                {
                    "symbol": symbol,
                    "action": "buy",
                    "quantity": int(parameters.get("quantity", 100)),
                    "reason": "正预期回报候选",
                }
            )
    return signals


def on_market(context, parameters):
    return []


def after_market(context, parameters):
    return []

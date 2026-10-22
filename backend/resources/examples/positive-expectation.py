def before_market(context, parameters):
    """以市值和历史预期回报筛选候选股票。"""
    # 每股分配组合权益的 1/预计持股数；10% 指该子仓位的 10%。
    # signal 自动预留预算；实盘未确认建议跨轮继续锁定，回测/快测模拟成交后释放。
    expected_holdings = int(parameters.get("expected_holdings", 10))
    ratio = parameters.get("ratio", "0.10")
    signals = []
    for symbol in context.universe():
        if context.position(symbol) > 0:
            continue
        value = context.factor("market.value", symbol=symbol)
        expected = context.factor("stat.expected-return", symbol=symbol)
        if value and expected["available"] and expected["expected_return"] > 0:
            bars = context.factor("market.daily-bars", symbol=symbol)
            if bars:
                signals.append(
                    context.signal(
                        symbol,
                        "buy",
                        ratio,
                        "正预期回报候选",
                        price=bars[-1]["close"],
                        expected_holdings=expected_holdings,
                    )
                )
    return [signal for signal in signals if signal["quantity"] > 0]


def on_market(context, parameters):
    return []


def after_market(context, parameters):
    return []

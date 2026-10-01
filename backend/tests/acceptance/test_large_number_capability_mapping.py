from easy_quant.domain.strategies.entities import StrategyRunStatus, StrategyVersion
from easy_quant.infrastructure.strategy_runtime.runner import SubprocessStrategyRunner

ADAPTED_STRATEGY = """def before_market(context, parameters):
    selected = []
    for symbol in context.universe():
        value = context.factor("market.value", symbol=symbol)
        finance = context.factor(
            "fundamental.latest", symbol=symbol, dataset="financial-indicators"
        )
        pledge = context.factor(
            "fundamental.latest", symbol=symbol, dataset="pledge-ratios"
        )
        rsi = context.factor("technical.rsi", symbol=symbol, window=3)
        if (
            value and finance and pledge and rsi["available"]
            and value["market_value"] <= parameters["max_market_value"]
            and finance["roe"] >= parameters["min_roe"]
            and pledge["pledge_ratio"] <= parameters["max_pledge_ratio"]
            and rsi["value"] < 80
        ):
            selected.append({
                "symbol": symbol,
                "action": "buy",
                "quantity": parameters["quantity"],
                "reason": "市值、财务、质押和技术条件通过",
            })
    return selected


def on_market(context, parameters):
    return [{
        "symbol": parameters["sell_symbol"],
        "action": "sell",
        "quantity": parameters["quantity"],
        "trigger_price": parameters["sell_price"],
        "reason": "到达盘中卖点",
    }]


def after_market(context, parameters):
    print("盘后持仓核对")
    return []
"""


def test_adapted_internal_strategy_can_select_and_run_three_hooks(fixed_now) -> None:
    version = StrategyVersion("v1", "s1", 1, ADAPTED_STRATEGY, "hash", fixed_now)
    context = {
        "universe": ["000001", "000002"],
        "prices": {
            "000001": [10, 10.5, 10.2, 10.8, 11],
            "000002": [10, 10.5, 10.2, 10.8, 11],
        },
        "market_values": {},
        "records": {
            "market-values": {
                "000001": [{"market_value": 80}],
                "000002": [{"market_value": 180}],
            },
            "financial-indicators": {
                "000001": [{"roe": 12}],
                "000002": [{"roe": 12}],
            },
            "pledge-ratios": {
                "000001": [{"pledge_ratio": 5}],
                "000002": [{"pledge_ratio": 5}],
            },
        },
    }
    parameters = {
        "max_market_value": 100,
        "min_roe": 10,
        "max_pledge_ratio": 10,
        "quantity": 100,
        "sell_symbol": "000001",
        "sell_price": 12,
    }
    runner = SubprocessStrategyRunner()

    before = runner.run(version, parameters, context, phase="before_market")
    intraday = runner.run(version, parameters, context, phase="on_market")
    after = runner.run(version, parameters, context, phase="after_market")

    assert before.status is StrategyRunStatus.SUCCEEDED
    assert [signal.symbol for signal in before.signals] == ["000001"]
    assert intraday.signals[0].trigger_price is not None
    assert after.signals == []
    assert "盘后持仓核对" in after.stdout

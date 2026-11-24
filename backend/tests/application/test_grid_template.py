from decimal import Decimal
from typing import Any

import pytest

from easy_quant.api.blueprints.strategies import GRID_TEMPLATE
from easy_quant.application.services.strategy_validation import PythonStrategyValidator
from easy_quant.strategy_api.context import RuntimeContext


@pytest.mark.parametrize(
    "price,quantity,action", [("9", "0", "buy"), ("11", "1000", "sell"), ("10", "500", None)]
)
def test_grid_parameters_target_inventory_and_lots(price, quantity, action):
    PythonStrategyValidator().validate(GRID_TEMPLATE)
    namespace: dict[str, Any] = {"Decimal": Decimal}
    exec(GRID_TEMPLATE, namespace)
    context = RuntimeContext(
        {
            "phase": "on_market",
            "cash": "5000",
            "positions": {"000001": quantity},
            "current_prices": {"000001": price},
        }
    )
    signals = namespace["on_market"](
        context, {"symbol": "000001", "anchor_price": "10", "grid_step": "0.05"}
    )
    if action is None:
        assert signals == []
    else:
        assert signals[0]["action"] == action
        assert Decimal(str(signals[0]["quantity"])) % 100 == 0


def test_grid_does_not_trade_on_dividend_and_adjusts_anchor_once():
    from tests.fakes.corporate_action_fixture import event

    namespace: dict[str, Any] = {"Decimal": Decimal}
    exec(GRID_TEMPLATE, namespace)
    state = {}
    data = {
        "phase": "on_market",
        "cash": "5000",
        "positions": {"000001": "500"},
        "trading_day": "2026-09-21",
        "decision_at": "2026-09-21T14:50:00+08:00",
        "corporate_actions": [event()],
        "current_prices": {"000001": "10"},
    }
    parameters = {"symbol": "000001", "anchor_price": "10"}
    assert namespace["on_market"](RuntimeContext(data, state=state), parameters) == []
    next_day = {
        **data,
        "trading_day": "2026-09-22",
        "decision_at": "2026-09-22T14:50:00+08:00",
        "cash": "5500",
        "current_prices": {"000001": "9"},
    }
    for _ in range(2):
        assert namespace["on_market"](RuntimeContext(next_day, state=state), parameters) == []
        assert Decimal(state["grid_anchor_price"]) == 9

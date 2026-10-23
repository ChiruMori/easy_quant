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

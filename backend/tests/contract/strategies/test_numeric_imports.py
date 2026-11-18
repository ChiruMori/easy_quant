from datetime import date

import pytest

from easy_quant.application.services.strategy_validation import PythonStrategyValidator
from easy_quant.domain.shared.errors import ValidationError
from easy_quant.domain.strategies.entities import StrategyRunStatus, StrategyVersion
from easy_quant.infrastructure.strategy_runtime.runner import (
    StreamingStrategyRunner,
    SubprocessStrategyRunner,
)
from tests.domain.factors.test_financial import financial_records

SOURCE = """import talib as ta
import numpy as np
from talib import RSI
from numpy import array, float64
HISTORY_TRADING_DAYS = 60
def before_market(c, p):
    bars = c.library('market.daily-bars', symbol='a')
    values = np.asarray([float(row['close']) for row in bars], dtype=np.float64)
    print(float(ta.SMA(values, timeperiod=3)[-1]))
    print(float(RSI(array([1,2,3,4,5], dtype=float64), timeperiod=3)[-1]))
    print(c.factor('roe_ttm', symbol='a'))
    return []
def on_market(c,p):
    return []
def after_market(c,p):
    return []
"""


def test_talib_and_financial_factor_execute_in_both_protocols(fixed_now):
    PythonStrategyValidator().validate(SOURCE)
    version = StrategyVersion("v", "s", 1, SOURCE, "h", fixed_now)
    records = financial_records()
    data = {
        "prices": {"a": ["1", "2", "3", "4", "5"]},
        "records": records,
        "decision_at": "2025-08-02T00:00:00+00:00",
    }
    run = SubprocessStrategyRunner().run(version, {}, data)
    assert run.status == StrategyRunStatus.SUCCEEDED, run.error
    assert run.stdout.startswith("4.0\n100.0\n{'available': True, 'value': 0.2666")
    with StreamingStrategyRunner(version, {}) as stream:
        streamed = stream.run_phase(
            date(2025, 8, 2),
            phase="before_market",
            expire_before=date(2025, 1, 1),
            prior_before=[
                {
                    "symbol": "a",
                    "trading_day": f"2025-07-{i:02}",
                    "close": str(i),
                    "available_at": "2025-08-01T00:00:00+00:00",
                }
                for i in range(1, 6)
            ],
            prior_after=[],
            today_after=[],
            today_symbols=[],
            current_prices={},
            positions={},
            cash="1000",
            records={"before_market": records},
            decision_at="2025-08-02T00:00:00+00:00",
        )
    assert streamed.status == StrategyRunStatus.SUCCEEDED, streamed.error
    assert streamed.stdout == run.stdout


@pytest.mark.parametrize(
    "code",
    [
        "import os",
        "import numpy.random",
        "from numpy import load",
        "from talib import *",
        "from . import talib",
        "import numpy as np\nnp.array([1]).tofile('x')",
        "import talib\ntalib.SMA.__globals__",
        "__builtins__['open']('x')",
    ],
)
def test_unsafe_imports_and_attributes_rejected_at_save_and_execution(code, fixed_now):
    source = code + "\n" + SOURCE
    with pytest.raises(ValidationError):
        PythonStrategyValidator().validate(source)
    run = SubprocessStrategyRunner().run(StrategyVersion("v", "s", 1, source, "h", fixed_now), {})
    assert run.status == StrategyRunStatus.FAILED


def test_talib_hidden_module_and_global_configuration_are_not_exposed(fixed_now):
    source = "from talib import set_unstable_period\n" + SOURCE
    run = SubprocessStrategyRunner().run(StrategyVersion("v", "s", 1, source, "h", fixed_now), {})
    assert run.status == StrategyRunStatus.FAILED
    assert "ValidationError" in (run.error or "")

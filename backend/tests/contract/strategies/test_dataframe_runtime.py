from datetime import date
from decimal import Decimal

import pytest

from easy_quant.domain.strategies.entities import StrategyVersion
from easy_quant.infrastructure.strategy_runtime.runner import (
    StreamingStrategyRunner,
    SubprocessStrategyRunner,
)
from easy_quant.strategy_api.context import RuntimeContext

SOURCE = """import pandas as pd
def before_market(c,p):
    frame = c.history('a')
    print(str(frame['close'].dtype), float(frame['close'].mean()))
    print(float(pd.Series([1, 2, 3]).rolling(2).mean().iloc[-1]))
    c.factor('technical.ma', symbol='a', window=2)
    c.factor('technical.ma', symbol='a', window=2)
    return []
"""


def test_legacy_decimal_strings_are_float64_and_cutoff_is_enforced():
    c = RuntimeContext(
        {
            "decision_at": "2026-09-25T16:00:00+08:00",
            "bars": {
                "a": [
                    {
                        "close": Decimal("10.1"),
                        "trading_day": "2026-09-24",
                        "available_at": "2026-09-24T15:00:00+08:00",
                    },
                    {
                        "close": "99",
                        "trading_day": "2026-09-26",
                        "available_at": "2026-09-26T15:00:00+08:00",
                    },
                ]
            },
        }
    )
    frame = c.history("a")
    assert str(frame["close"].dtype) == "float64"
    assert frame["close"].tolist() == [10.1]
    frame.loc[0, "close"] = 100
    assert c.history("a")["close"].tolist() == [10.1]


def test_dataframe_and_metrics_roundtrip_in_both_protocols(fixed_now):
    version = StrategyVersion("v", "s", 1, SOURCE, "h", fixed_now)
    rows: list[dict[str, object]] = [
        {
            "symbol": "a",
            "close": str(value),
            "trading_day": "2026-09-24",
            "available_at": "2026-09-24T15:00:00+08:00",
        }
        for value in [10, 12]
    ]
    single = SubprocessStrategyRunner().run(version, {}, {"bars": {"a": rows}})
    assert single.status == "succeeded", single.error
    assert single.stdout == "float64 11.0\n2.5\n"
    assert single.factor_metrics["technical.ma"]["calls"] == 2
    assert single.factor_metrics["technical.ma"]["elapsed_ns"] > 0
    with StreamingStrategyRunner(version, {}) as runner:
        run = runner.run_phase(
            date(2026, 9, 25),
            phase="before_market",
            expire_before=date(2026, 9, 1),
            prior_before=rows[:1],
            prior_after=[],
            today_after=[],
            today_symbols=[],
            current_prices={},
            positions={},
            cash="1000",
        )
    assert run.status == "succeeded", run.error
    assert "float64 10.0" in run.stdout
    assert run.factor_metrics["technical.ma"]["calls"] == 2
    assert run.factor_event_id != single.factor_event_id


@pytest.mark.parametrize(
    "statement",
    [
        "import pandas.io",
        "from pandas import read_csv",
        "import pandas as pd\npd.DataFrame().to_csv('x')",
        "import pandas as pd\npd.Series([1]).agg('to_csv')",
        "import pandas as pd\npd.DataFrame().query('x')",
    ],
)
def test_pandas_io_and_expression_dispatch_are_rejected(statement, fixed_now):
    run = SubprocessStrategyRunner().run(
        StrategyVersion("v", "s", 1, statement, "h", fixed_now), {}
    )
    assert run.status == "failed"


def test_failed_factor_call_is_returned_in_metrics(fixed_now):
    source = "def before_market(c,p):\n c.factor('technical.ma', symbol='a', window=0)\n return []"
    run = SubprocessStrategyRunner().run(StrategyVersion("v", "s", 1, source, "h", fixed_now), {})
    assert run.status == "failed"
    assert run.factor_metrics["technical.ma"]["calls"] == 1


def test_numpy_arrays_and_dataframes_can_be_printed_without_exposing_modules(fixed_now):
    source = (
        "import numpy as np\nimport pandas as pd\n"
        "def before_market(c,p):\n"
        " print(np.array([1,2,3]))\n print(pd.DataFrame({'x':[1.0,2.0]}))\n return []"
    )
    run = SubprocessStrategyRunner().run(StrategyVersion("v", "s", 1, source, "h", fixed_now), {})
    assert run.status == "succeeded", run.error
    assert "[1 2 3]" in run.stdout and "2.0" in run.stdout

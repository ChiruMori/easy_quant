from datetime import date

import pytest

from easy_quant.application.services.factor_quick_test import quick_test_factor
from easy_quant.domain.shared.errors import StateConflictError, ValidationError
from tests.fakes.platform import make_test_container


def prepared():
    container = make_test_container()
    container.market_data.upsert_bars(
        [
            {
                "symbol": "a",
                "trading_day": f"2026-09-{day}",
                "close": str(day),
                "available_at": f"2026-09-{day}T15:00:00+08:00",
            }
            for day in range(21, 26)
        ]
    )
    return container


def test_real_subprocess_quick_test_reads_only_requested_symbol_and_excludes_future():
    container = prepared()
    result = quick_test_factor(
        container, "technical.ma", {"symbol": "a", "window": 5}, date(2026, 9, 25)
    )
    assert result["result"] == {"available": True, "value": 23.0, "window": 5}
    assert result["rows"] == 5 and result["mock"] is False
    assert container.factor_statistics.snapshot() == {}
    early = quick_test_factor(
        container, "technical.ma", {"symbol": "a", "window": 5}, date(2026, 9, 24)
    )
    assert early["result"]["available"] is False


@pytest.mark.parametrize(
    "parameters",
    [
        {"symbol": "a", "window": 2501},
        {"symbol": "a", "window": True},
        {"symbol": "a", "window": "1.5"},
        {"symbol": "a", "typo": 1},
        {"symbol": "a", "symbols": "a"},
    ],
)
def test_quick_test_rejects_invalid_inputs_before_execution(parameters):
    with pytest.raises(ValidationError):
        quick_test_factor(prepared(), "technical.ma", parameters, date(2026, 9, 25))


def test_quick_test_hard_timeout_kills_isolated_computation():
    # 数据准备为内存fake；0.1秒不足以启动并完成pandas计算，走实际subprocess超时清理。
    with pytest.raises(StateConflictError, match="超时"):
        quick_test_factor(
            prepared(), "technical.ma", {"symbol": "a"}, date(2026, 9, 25), timeout_seconds=0.1
        )

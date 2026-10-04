import pytest

from easy_quant.application.services.strategies import StrategyService
from easy_quant.application.services.strategy_validation import (
    PythonStrategyValidator,
    extract_history_trading_days,
)
from easy_quant.domain.shared.errors import ValidationError
from easy_quant.infrastructure.persistence.repositories.strategies import InMemoryStrategyRepository
from tests.fakes.core import FixedClock, SequentialIdGenerator


def test_versions_are_immutable_and_linked(fixed_now) -> None:
    repository = InMemoryStrategyRepository()
    service = StrategyService(
        repository, PythonStrategyValidator(), FixedClock(fixed_now), SequentialIdGenerator()
    )
    empty_hooks = (
        "def before_market(context, parameters):\n return []\n"
        "def on_market(context, parameters):\n return []\n"
        "def after_market(context, parameters):\n return []"
    )
    strategy, first = service.create("user", "demo", empty_hooks)
    second = service.add_version(
        strategy.id,
        empty_hooks.replace("return []", 'return [{"symbol": "x"}]', 1),
    )
    assert second.parent_version_id == first.id
    assert first.source_code.endswith("return []")
    assert first.content_sha256 != second.content_sha256


def test_strategy_history_window_requires_bounded_literal() -> None:
    assert extract_history_trading_days("def before_market(context, parameters): pass") == 250
    assert extract_history_trading_days("HISTORY_TRADING_DAYS = 600") == 600
    for source in (
        "HISTORY_TRADING_DAYS = 0",
        "HISTORY_TRADING_DAYS = 2501",
        "HISTORY_TRADING_DAYS = True",
        "HISTORY_TRADING_DAYS = parameters",
        "HISTORY_TRADING_DAYS = 300\nHISTORY_TRADING_DAYS = 400",
    ):
        with pytest.raises(ValidationError, match="HISTORY_TRADING_DAYS"):
            extract_history_trading_days(source)

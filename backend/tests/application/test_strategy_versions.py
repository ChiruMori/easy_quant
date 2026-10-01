from easy_quant.application.services.strategies import StrategyService
from easy_quant.application.services.strategy_validation import PythonStrategyValidator
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

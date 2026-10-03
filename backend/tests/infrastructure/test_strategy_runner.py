from easy_quant.domain.strategies.entities import StrategyRunStatus, StrategyVersion
from easy_quant.infrastructure.strategy_runtime.runner import SubprocessStrategyRunner


def version(source, fixed_now):
    return StrategyVersion("v1", "s1", 1, source, "hash", fixed_now)


def test_subprocess_success_and_exception(fixed_now) -> None:
    source = (
        'def before_market(context, parameters):\n return [{"symbol":"000001",'
        '"action":"buy","quantity":100}]'
    )
    success = SubprocessStrategyRunner().run(
        version(source, fixed_now),
        {},
    )
    assert success.status is StrategyRunStatus.SUCCEEDED
    failure = SubprocessStrategyRunner().run(
        version("def before_market(context, parameters):\n raise ValueError('bad')", fixed_now), {}
    )
    assert failure.status is StrategyRunStatus.FAILED


def test_subprocess_timeout_and_output_limit(fixed_now) -> None:
    timeout = SubprocessStrategyRunner(timeout_seconds=0.1).run(
        version("def before_market(context, parameters):\n while True: pass", fixed_now), {}
    )
    assert timeout.status is StrategyRunStatus.TIMED_OUT
    noisy = SubprocessStrategyRunner(output_limit=20).run(
        version(
            "def before_market(context, parameters):\n print('x' * 100)\n return []", fixed_now
        ),
        {},
    )
    assert noisy.status is StrategyRunStatus.FAILED


def test_many_signals_do_not_count_as_standard_output(fixed_now) -> None:
    source = (
        "def before_market(context, parameters):\n"
        " return [{'symbol': symbol, 'action': 'buy', 'quantity': 100} "
        "for symbol in context.universe()]"
    )
    symbols = [f"{index:06d}" for index in range(6000)]
    result = SubprocessStrategyRunner().run(version(source, fixed_now), {}, {"universe": symbols})
    assert result.status is StrategyRunStatus.SUCCEEDED
    assert len(result.signals) == 6000
    assert result.stdout == ""


def test_transport_limit_is_distinct_and_never_echoes_json(fixed_now) -> None:
    source = (
        "def before_market(context, parameters):\n"
        " return [{'symbol': symbol, 'action': 'buy', 'quantity': 100} "
        "for symbol in context.universe()]"
    )
    result = SubprocessStrategyRunner(result_limit=100).run(
        version(source, fixed_now), {}, {"universe": ["000001", "000002"]}
    )
    assert result.status is StrategyRunStatus.FAILED
    assert result.error == "策略结果超过传输限制"
    assert result.stdout == ""

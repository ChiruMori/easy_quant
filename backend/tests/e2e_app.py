from threading import Thread

from easy_quant.api.app import create_app
from easy_quant.infrastructure.core import SystemSleeper
from easy_quant.worker.handlers.backtests import register_backtest_handlers
from easy_quant.worker.handlers.market_data import register_market_data_handlers
from easy_quant.worker.handlers.strategies import register_strategy_handlers
from easy_quant.worker.registry import JobHandlerRegistry
from easy_quant.worker.runner import Worker
from tests.fakes.platform import make_test_container, make_test_settings


def create_e2e_app():
    """Playwright 专用应用：显式注入离线替身，不属于运行环境装配。"""

    settings = make_test_settings()
    container = make_test_container(settings, initialize_admin=True)
    registry = JobHandlerRegistry()
    register_backtest_handlers(registry, container)
    register_strategy_handlers(registry, container)
    register_market_data_handlers(registry, container)
    worker = Worker(
        "e2e-worker",
        container.jobs,
        registry,
        container.authentication.clock,
        SystemSleeper(),
        poll_seconds=0.1,
    )
    Thread(target=worker.run_forever, daemon=True).start()
    return create_app(settings=settings, container=container)

from threading import Thread

from easy_quant.api.app import create_app
from easy_quant.application.services.market_data_sync import MarketDataSyncService
from easy_quant.domain.market_data.indices import is_index
from easy_quant.infrastructure.core import SystemSleeper
from easy_quant.worker.handlers.backtests import register_backtest_handlers
from easy_quant.worker.handlers.market_data import register_market_data_handlers
from easy_quant.worker.handlers.strategies import register_strategy_handlers
from easy_quant.worker.registry import JobHandlerRegistry
from easy_quant.worker.runner import Worker
from tests.fakes.index_data import FixtureCalendarAcquisition, FixtureIndexAcquisition
from tests.fakes.platform import make_test_container, make_test_settings


def create_e2e_app():
    """Playwright 专用应用：显式注入离线替身，不属于运行环境装配。"""

    settings = make_test_settings()
    container = make_test_container(settings, initialize_admin=True)
    # 与 0014 数据迁移相同的离线初始计划；不访问数据库。
    container.state.schedules["schedule-index-daily-update"] = {
        "id": "schedule-index-daily-update",
        "task_type": "index-daily-update",
        "schedule_kind": "cron",
        "schedule_expression": "0 22 * * 1-5",
        "timezone": "Asia/Shanghai",
        "enabled": False,
        "configuration": {},
        "next_run_at": "1970-01-01T00:00:00+00:00",
    }

    class OfflineNotificationChannel:
        def send(self, *_args):
            return None

    for channel in ("ntfy", "dingtalk", "feishu", "wecom"):
        container.notification_channels[channel] = OfflineNotificationChannel()

    class OfflineManagementSyncV1(MarketDataSyncService):
        """管理旅程验证入队；实际指数同步使用版本化 fixture，其余同步由服务层测试覆盖。"""

        def sync(self, dataset_key, **kwargs):
            if dataset_key not in {"daily-bars", "trading-calendar"} or (
                dataset_key == "daily-bars"
                and any(not is_index(symbol) for symbol in kwargs.get("symbols", []))
            ):
                return {"record_count": 0, "attempts": [], "source_key": "offline-management-v1"}
            return super().sync(dataset_key, **kwargs)

    container.data_sync = OfflineManagementSyncV1(
        {
            "daily-bars": FixtureIndexAcquisition(container.authentication.clock),
            "trading-calendar": FixtureCalendarAcquisition(container.authentication.clock),
        },
        container.market_data,
    )
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

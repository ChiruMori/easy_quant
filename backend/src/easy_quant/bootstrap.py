from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from easy_quant.application.services.acquisition import AcquisitionService, ExponentialRetry
from easy_quant.application.services.authentication import AuthenticationService
from easy_quant.application.services.market_data_sync import MarketDataSyncService
from easy_quant.config import Settings, get_settings
from easy_quant.infrastructure.core import SystemClock, SystemSleeper, UuidGenerator
from easy_quant.infrastructure.data_sources.akshare.adapters import AkShareSource
from easy_quant.infrastructure.data_sources.eastmoney.adapters import EastMoneySource
from easy_quant.infrastructure.data_sources.eastmoney.client import EastMoneyClient
from easy_quant.infrastructure.persistence.repositories.identity import SqlAlchemyIdentityRepository
from easy_quant.infrastructure.persistence.repositories.jobs import SqlAlchemyJobRepository
from easy_quant.infrastructure.persistence.repositories.raw_cache import (
    SqlAlchemyCompressedRawCache,
)
from easy_quant.infrastructure.persistence.repositories.runtime import (
    InMemoryBacktestStore,
    InMemoryMarketDataStore,
    SqlAlchemyBacktestStore,
    SqlAlchemyMarketDataStore,
)
from easy_quant.infrastructure.persistence.repositories.runtime_documents import (
    SqlJsonDict,
    SqlJsonList,
)
from easy_quant.infrastructure.persistence.repositories.strategies import (
    InMemoryStrategyRepository,
    SqlAlchemyStrategyRepository,
)
from easy_quant.infrastructure.persistence.session import (
    create_database_engine,
    create_session_factory,
)
from easy_quant.infrastructure.security import SecretBox


def _default_datasets() -> list[dict[str, Any]]:
    return [
        {
            "key": "securities",
            "name": "证券列表",
            "description": "沪深股票代码、名称与交易所",
            "sources": [
                {"key": "eastmoney", "name": "东方财富", "enabled": True},
                {"key": "akshare", "name": "AKShare", "enabled": True},
            ],
        },
        {
            "key": "daily-bars",
            "name": "日线 K 线",
            "description": "前复权日线开高低收与成交量",
            "sources": [
                {"key": "akshare", "name": "AKShare", "enabled": True},
                {"key": "eastmoney", "name": "东方财富", "enabled": True},
            ],
        },
        {
            "key": "trading-calendar",
            "name": "交易日历",
            "description": "交易日判断、上一交易日和盘后更新范围",
            "sources": [{"key": "akshare", "name": "AKShare", "enabled": True}],
        },
        {
            "key": "market-values",
            "name": "估值与市值",
            "description": "市盈率、市净率、总市值与流通市值",
            "sources": [{"key": "eastmoney", "name": "东方财富", "enabled": True}],
        },
        {
            "key": "pledge-ratios",
            "name": "股票质押率",
            "description": "股票质押比例与质押数量",
            "sources": [{"key": "akshare", "name": "AKShare", "enabled": True}],
        },
        {
            "key": "financial-indicators",
            "name": "财务指标",
            "description": "按报告期保存的历史财务分析指标",
            "sources": [{"key": "akshare", "name": "AKShare", "enabled": True}],
        },
    ]


@dataclass(slots=True)
class PlatformState:
    strategies: Any = field(default_factory=InMemoryStrategyRepository)
    datasets: Any = field(default_factory=_default_datasets)
    acquisitions: Any = field(default_factory=dict)
    backtests: dict[str, dict[str, Any]] = field(default_factory=dict)
    daily_bars: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    instruments: dict[str, dict[str, Any]] = field(default_factory=dict)
    import_previews: Any = field(default_factory=dict)
    trading_days: set[str] = field(default_factory=set)
    market_records: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    subscriptions: Any = field(default_factory=list)
    deliveries: Any = field(default_factory=list)
    live_instances: Any = field(default_factory=dict)
    recommendations: Any = field(default_factory=dict)
    operations: Any = field(default_factory=dict)
    portfolio_ledger: Any = field(default_factory=list)
    schedules: Any = field(default_factory=dict)
    jobs: Any = field(default_factory=list)
    audit_events: Any = field(default_factory=list)


@dataclass(slots=True)
class Container:
    settings: Settings
    authentication: AuthenticationService
    state: PlatformState = field(default_factory=PlatformState)
    market_data: Any = None
    backtests: Any = None
    database_session: Any = None
    data_sync: MarketDataSyncService | None = None
    jobs: Any = None
    secret_box: SecretBox | None = None
    notification_channels: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.secret_box is None:
            secret = (
                self.settings.credential_encryption_key.get_secret_value()
                if self.settings.credential_encryption_key is not None
                else self.settings.secret_key.get_secret_value()
            )
            self.secret_box = SecretBox(secret)
        if self.market_data is None:
            self.market_data = InMemoryMarketDataStore(
                self.state.daily_bars,
                self.state.instruments,
                self.state.trading_days,
                self.state.market_records,
            )
        if self.backtests is None:
            self.backtests = InMemoryBacktestStore(self.state.backtests)


def build_container(settings: Settings | None = None) -> Container:
    """装配真实运行时；所有环境都使用配置的数据库，不提供易失回退。"""

    settings = settings or get_settings()
    engine = create_database_engine(settings.database_url.get_secret_value())
    session = create_session_factory(engine)()
    identity = SqlAlchemyIdentityRepository(session)
    strategies = SqlAlchemyStrategyRepository(session)
    datasets = SqlJsonList(session, "datasets")
    if not datasets:
        for dataset in _default_datasets():
            datasets.append(dataset)
    state = PlatformState(
        strategies=strategies,
        datasets=datasets,
        acquisitions=SqlJsonDict(session, "acquisitions"),
        import_previews=SqlJsonDict(session, "import_previews"),
        subscriptions=SqlJsonList(session, "subscriptions"),
        deliveries=SqlJsonList(session, "deliveries"),
        live_instances=SqlJsonDict(session, "live_instances"),
        recommendations=SqlJsonDict(session, "recommendations"),
        operations=SqlJsonDict(session, "operations"),
        portfolio_ledger=SqlJsonList(session, "portfolio_ledger"),
        schedules=SqlJsonDict(session, "schedules"),
        jobs=SqlJsonList(session, "jobs"),
        audit_events=SqlJsonList(session, "audit_events"),
    )
    container = Container(
        settings=settings,
        authentication=AuthenticationService(identity, SystemClock(), UuidGenerator()),
        state=state,
        market_data=SqlAlchemyMarketDataStore(session),
        backtests=SqlAlchemyBacktestStore(session),
        database_session=session,
        jobs=SqlAlchemyJobRepository(session),
    )
    raw_cache = SqlAlchemyCompressedRawCache(session)
    container.data_sync = _build_market_data_sync(container, raw_cache)
    encryption_secret = (
        settings.credential_encryption_key.get_secret_value()
        if settings.credential_encryption_key is not None
        else settings.secret_key.get_secret_value()
    )
    container.secret_box = SecretBox(encryption_secret)
    container.notification_channels = _build_notification_channels(settings)
    if not identity.has_any_user():
        container.authentication.initialize_admin(
            settings.initial_admin_username, settings.initial_admin_password.get_secret_value()
        )
    return container


def _build_notification_channels(settings: Settings) -> dict[str, Any]:
    import httpx

    from easy_quant.infrastructure.notifications.email import EmailChannel
    from easy_quant.infrastructure.notifications.ntfy import NtfyChannel

    channels: dict[str, Any] = {
        "ntfy": NtfyChannel(httpx.Client(timeout=10.0), settings.ntfy_base_url)
    }
    if settings.smtp_host and settings.smtp_sender:
        channels["email"] = EmailChannel(
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_sender,
            settings.smtp_username,
            settings.smtp_password.get_secret_value() if settings.smtp_password else None,
        )
    return channels


def _build_market_data_sync(container: Container, raw_cache: Any) -> MarketDataSyncService:
    import akshare as ak
    import httpx
    import pandas as pd

    clock, sleeper = SystemClock(), SystemSleeper()
    eastmoney = EastMoneySource(EastMoneyClient(httpx.Client(timeout=20.0)))

    def akshare_securities(**_: object):
        sh = ak.stock_info_sh_name_code().rename(
            columns={"证券代码": "code", "证券简称": "name", "上市日期": "listed_on"}
        )
        sz = ak.stock_info_sz_name_code().rename(
            columns={"A股代码": "code", "A股简称": "name", "A股上市日期": "listed_on"}
        )
        bj = ak.stock_info_bj_name_code().rename(
            columns={"证券代码": "code", "证券简称": "name", "上市日期": "listed_on"}
        )
        columns = ["code", "name", "listed_on"]
        return pd.concat(
            [frame.reindex(columns=columns) for frame in (sh, sz, bj)], ignore_index=True
        )

    securities_ak = AkShareSource({"securities": akshare_securities})
    daily_ak = AkShareSource(
        {
            "daily-bars": lambda **parameters: ak.stock_zh_a_hist(
                symbol=str(parameters["symbol"]),
                period="daily",
                start_date=str(parameters["start_date"]).replace("-", ""),
                end_date=str(parameters["end_date"]).replace("-", ""),
                adjust="qfq",
            )
        }
    )
    calendar_ak = AkShareSource({"trading-calendar": lambda **_: ak.tool_trade_date_hist_sina()})
    quotes_ak = AkShareSource({"live-quotes": lambda **_: ak.stock_zh_a_spot_em()})
    pledge_ak = AkShareSource(
        {
            "pledge-ratios": lambda **parameters: ak.stock_gpzy_pledge_ratio_em(
                date=str(parameters["date"])
            )
        }
    )
    financial_ak = AkShareSource(
        {
            "financial-indicators": lambda **parameters: ak.stock_financial_analysis_indicator(
                symbol=str(parameters["symbol"]), start_year=str(parameters["start_year"])
            )
        }
    )

    def acquisition(sources: list[Any]) -> AcquisitionService:
        return AcquisitionService(
            sources,
            raw_cache,
            clock,
            sleeper,
            retry=ExponentialRetry(max_attempts=2, base_seconds=0.5),
        )

    quotes_acquisition = AcquisitionService(
        [quotes_ak, eastmoney],
        raw_cache,
        clock,
        sleeper,
        retry=ExponentialRetry(max_attempts=2, base_seconds=0.5),
        freshness=timedelta(seconds=30),
    )

    return MarketDataSyncService(
        {
            "securities": acquisition([securities_ak, eastmoney]),
            "daily-bars": acquisition([daily_ak, eastmoney]),
            "trading-calendar": acquisition([calendar_ak]),
            "live-quotes": quotes_acquisition,
            "market-values": acquisition([eastmoney]),
            "pledge-ratios": acquisition([pledge_ak]),
            "financial-indicators": acquisition([financial_ak]),
        },
        container.market_data,
    )


def build_worker():
    from datetime import datetime, time
    from zoneinfo import ZoneInfo

    from easy_quant.application.services.scheduled_tasks import next_run
    from easy_quant.domain.market_data.calendar import TradingCalendar
    from easy_quant.domain.scheduling.entities import ScheduledTask, ScheduleKind
    from easy_quant.worker.handlers.live_tracking import register_live_handlers
    from easy_quant.worker.handlers.market_data import register_market_data_handlers
    from easy_quant.worker.handlers.notifications import register_notification_handlers
    from easy_quant.worker.registry import JobHandlerRegistry
    from easy_quant.worker.runner import Worker

    settings = get_settings()
    container = build_container(settings)
    registry = JobHandlerRegistry()
    register_market_data_handlers(registry, container)
    register_live_handlers(registry, container)
    register_notification_handlers(registry, container)

    def advance_schedule(schedule_id: str, schedule: dict[str, object], now: datetime) -> None:
        raw_configuration = schedule.get("configuration", {})
        configuration = raw_configuration if isinstance(raw_configuration, dict) else {}
        task = ScheduledTask(
            schedule_id,
            str(schedule["task_type"]),
            ScheduleKind(str(schedule.get("schedule_kind", "cron"))),
            str(schedule.get("schedule_expression", "0 18 * * 1-5")),
            str(schedule.get("timezone", "Asia/Shanghai")),
            {str(key): value for key, value in configuration.items()},
            now,
        )
        schedule["next_run_at"] = next_run(task, now).isoformat()
        container.state.schedules[schedule_id] = schedule

    def pump_schedules() -> None:
        now = container.authentication.clock.now()
        for schedule_id, schedule in list(container.state.schedules.items()):
            if not schedule.get("enabled", True):
                continue
            next_run_at = schedule.get("next_run_at")
            if not next_run_at or datetime.fromisoformat(str(next_run_at)) > now:
                continue
            job_type = str(schedule["task_type"])
            payload = dict(schedule.get("configuration", {}))
            calendar = TradingCalendar(container.market_data.list_trading_days() or None)
            local_now = now.astimezone(ZoneInfo("Asia/Shanghai"))
            if job_type == "live-analysis":
                phase = payload.get("phase")
                in_morning = time(9, 30) <= local_now.time() <= time(11, 30)
                in_afternoon = time(13, 0) <= local_now.time() <= time(15, 0)
                if not calendar.is_trading_day(local_now.date()) or (
                    phase == "on_market" and not (in_morning or in_afternoon)
                ):
                    advance_schedule(schedule_id, schedule, now)
                    continue
            if job_type == "market-data-acquisition" and payload.get("mode") == "daily-update":
                payload["end_day"] = calendar.previous_trading_day(now.date()).isoformat()
                payload["start_day"] = payload["end_day"]
                payload["symbols"] = [
                    str(item["symbol"]) for item in container.market_data.list_instruments()
                ]
                payload["dataset_key"] = "daily-bars"
            from easy_quant.domain.scheduling.entities import Job

            due = str(next_run_at)
            container.jobs.enqueue(
                Job(UuidGenerator().new(), job_type, f"{schedule_id}:{due}", payload, now)
            )
            advance_schedule(schedule_id, schedule, now)

    return Worker(
        worker_id="single-worker",
        jobs=container.jobs,
        handlers=registry,
        clock=SystemClock(),
        sleeper=SystemSleeper(),
        poll_seconds=settings.worker_poll_seconds,
        poll_hook=pump_schedules,
    )

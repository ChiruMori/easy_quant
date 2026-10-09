from datetime import UTC, datetime

from flask import Blueprint, g, request

from easy_quant.api.dependencies import get_container
from easy_quant.api.middleware.auth import require_user
from easy_quant.api.responses import success
from easy_quant.api.schemas.strategies import StrategyCreateRequest, StrategyRunRequest
from easy_quant.application.services.audit_runtime import record_audit
from easy_quant.application.services.strategies import StrategyService
from easy_quant.application.services.strategy_validation import PythonStrategyValidator
from easy_quant.domain.scheduling.entities import Job
from easy_quant.infrastructure.core import UuidGenerator

blueprint = Blueprint("strategies", __name__, url_prefix="/api/v1/strategies")
MOVING_AVERAGE_TEMPLATE = '''def before_market(context, parameters):
    """盘前使用此前已知日线，选择价格站上 5 日均线的股票。"""
    ratio = parameters.get("ratio", "0.10")
    signals = []
    for symbol in context.universe():
        bars = context.factor("market.daily-bars", symbol=symbol)
        ma5 = context.factor("technical.ma", symbol=symbol, window=5)
        if ma5["available"] and bars[-1]["close"] > ma5["value"]:
            signals.append(context.signal(
                symbol, "buy", ratio, "收盘价站上 5 日均线", price=bars[-1]["close"]
            ))
    return signals


def on_market(context, parameters):
    """声明盘中触发价；平台每天统一时刻判断一次，不会自动下单。"""
    trigger = parameters.get("intraday_buy_price")
    if trigger is None:
        return []
    signals = []
    for symbol in context.universe():
        if context.position(symbol) == 0:
            signals.append(context.signal(
                symbol, "buy", parameters.get("ratio", "0.10"),
                "盘中价格到达预设买点", price=trigger, trigger_price=trigger,
            ))
    return signals


def after_market(context, parameters):
    """盘后可读取当日收盘数据，本示例只输出运行信息。"""
    return []
'''

POSITIVE_EXPECTATION_TEMPLATE = '''def before_market(context, parameters):
    """以市值和历史预期回报筛选候选股票。"""
    ratio = parameters.get("ratio", "0.10")
    signals = []
    for symbol in context.universe():
        value = context.factor("market.value", symbol=symbol)
        expected = context.factor("stat.expected-return", symbol=symbol)
        if value and expected["available"] and expected["expected_return"] > 0:
            bars = context.factor("market.daily-bars", symbol=symbol)
            if bars:
                signals.append(context.signal(
                    symbol, "buy", ratio, "正预期回报候选", price=bars[-1]["close"]
                ))
    return signals


def on_market(context, parameters):
    return []


def after_market(context, parameters):
    return []
'''


def repository():
    return get_container().state.strategies


def strategy_service() -> StrategyService:
    return StrategyService(repository(), PythonStrategyValidator(), ApiClock(), UuidGenerator())


class ApiClock:
    def now(self):
        return datetime.now(UTC)


def serialize(strategy):
    versions = repository().versions(strategy.id)
    return {
        "id": strategy.id,
        "name": strategy.name,
        "description": strategy.description,
        "current_version_id": strategy.current_version_id,
        "versions": [
            {
                "id": version.id,
                "number": version.number,
                "source_code": version.source_code,
                "created_at": version.created_at.isoformat(),
            }
            for version in versions
        ],
    }


@blueprint.get("")
@require_user
def list_strategies():
    return success(
        [
            serialize(item)
            for item in repository().definitions.values()
            if item.owner_id == g.current_user.id
        ]
    )


@blueprint.post("")
@require_user
def create_strategy():
    payload = StrategyCreateRequest.model_validate(request.get_json() or {})
    strategy, version = strategy_service().create(
        g.current_user.id, payload.name, payload.source_code, payload.description
    )
    record_audit(
        get_container(),
        actor_user_id=g.current_user.id,
        action="create",
        resource_type="strategy",
        resource_id=strategy.id,
        after={"version_id": version.id, "version": version.number},
    )
    return success({**serialize(strategy), "version": version.number}, status=201)


@blueprint.post("/<strategy_id>/versions")
@require_user
def add_version(strategy_id: str):
    payload = StrategyCreateRequest.model_validate(
        {"name": "version", **(request.get_json() or {})}
    )
    strategy = repository().get_definition(strategy_id)
    if strategy is None or strategy.owner_id != g.current_user.id:
        return success(None, status=404)
    version = strategy_service().add_version(strategy_id, payload.source_code)
    record_audit(
        get_container(),
        actor_user_id=g.current_user.id,
        action="create_version",
        resource_type="strategy",
        resource_id=strategy_id,
        after={"version_id": version.id, "version": version.number},
    )
    return success(
        {
            "id": version.id,
            "number": version.number,
            "parent_version_id": version.parent_version_id,
        },
        status=201,
    )


@blueprint.post("/<strategy_id>/run")
@require_user
def run_strategy(strategy_id: str):
    payload = StrategyRunRequest.model_validate(request.get_json() or {})
    strategy = repository().get_definition(strategy_id)
    if strategy is None or strategy.owner_id != g.current_user.id:
        return success(None, status=404)
    version = repository().versions(strategy_id)[-1]
    identifier = f"job-{UuidGenerator().new()}"
    job = get_container().jobs.enqueue(
        Job(
            identifier,
            "strategy.run",
            f"strategy-run:{identifier}",
            {
                "owner_id": g.current_user.id,
                "strategy_id": strategy_id,
                "strategy_version_id": version.id,
                "trading_day": payload.trading_day.isoformat(),
                "parameters": payload.parameters,
                "allow_mock": payload.allow_mock,
                "initial_cash": str(payload.initial_cash),
            },
            get_container().authentication.clock.now(),
        )
    )
    record_audit(
        get_container(),
        actor_user_id=g.current_user.id,
        action="run",
        resource_type="strategy",
        resource_id=strategy_id,
        after={"status": job.status.value, "version_id": version.id, "job_id": job.id},
    )
    return success(
        {
            "id": job.id,
            "status": job.status.value,
            "strategy_version_id": version.id,
            "trading_day": payload.trading_day.isoformat(),
            "phase_results": [],
        },
        status=202,
    )


@blueprint.get("/<strategy_id>/runs")
@require_user
def list_strategy_runs(strategy_id: str):
    strategy = repository().get_definition(strategy_id)
    if strategy is None or strategy.owner_id != g.current_user.id:
        return success(None, status=404)
    rows = []
    for job in get_container().jobs.list_all():
        if job.job_type != "strategy.run" or job.payload.get("strategy_id") != strategy_id:
            continue
        rows.append(
            {
                "id": job.id,
                "status": job.status.value,
                "strategy_version_id": job.payload.get("strategy_version_id"),
                "trading_day": job.payload.get("trading_day"),
                "phase_results": job.result_summary.get("phase_results")
                or job.error_summary.get("details", {}).get("phase_results", []),
                "error": job.error_summary.get("message"),
                "mock_usage": job.result_summary.get("mock_usage", []),
                "allow_mock": job.payload.get("allow_mock", False),
                "portfolio": job.result_summary.get("portfolio"),
                "trades": job.result_summary.get("trades", []),
            }
        )
    return success(list(reversed(rows)))


@blueprint.get("/templates")
@require_user
def templates():
    return success(
        [
            {
                "key": "moving-average",
                "name": "5 日均线选股",
                "source_code": MOVING_AVERAGE_TEMPLATE,
            },
            {
                "key": "positive-expectation",
                "name": "正预期示例",
                "source_code": POSITIVE_EXPECTATION_TEMPLATE,
            },
        ]
    )

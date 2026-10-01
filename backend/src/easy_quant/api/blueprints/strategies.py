from datetime import UTC, datetime

from flask import Blueprint, g, request

from easy_quant.api.dependencies import get_container
from easy_quant.api.middleware.auth import require_user
from easy_quant.api.responses import success
from easy_quant.api.schemas.strategies import StrategyCreateRequest, StrategyRunRequest
from easy_quant.application.services.audit_runtime import record_audit
from easy_quant.application.services.strategies import StrategyService
from easy_quant.application.services.strategy_validation import (
    PythonStrategyValidator,
    extract_factor_dependencies,
)
from easy_quant.domain.shared.errors import StateConflictError
from easy_quant.infrastructure.core import UuidGenerator
from easy_quant.infrastructure.strategy_runtime.runner import SubprocessStrategyRunner

blueprint = Blueprint("strategies", __name__, url_prefix="/api/v1/strategies")
MOVING_AVERAGE_TEMPLATE = '''def before_market(context, parameters):
    """盘前使用此前已知日线，选择价格站上 5 日均线的股票。"""
    quantity = int(parameters.get("quantity", 100))
    signals = []
    for symbol in context.universe():
        bars = context.factor("market.daily-bars", symbol=symbol)
        ma5 = context.factor("technical.ma", symbol=symbol, window=5)
        if ma5["available"] and bars[-1]["close"] > ma5["value"]:
            signals.append({
                "symbol": symbol,
                "action": "buy",
                "quantity": quantity,
                "reason": "收盘价站上 5 日均线",
            })
    return signals


def on_market(context, parameters):
    """声明盘中触发价；平台盯盘命中条件后才通知，且不会自动下单。"""
    trigger = parameters.get("intraday_buy_price")
    if trigger is None:
        return []
    signals = []
    for symbol in context.universe():
        if context.position(symbol) == 0:
            signals.append({
                "symbol": symbol,
                "action": "buy",
                "quantity": int(parameters.get("quantity", 100)),
                "trigger_price": trigger,
                "reason": "盘中价格到达预设买点",
            })
    return signals


def after_market(context, parameters):
    """盘后可读取当日收盘数据，本示例只输出运行信息。"""
    print("盘后检查完成")
    return []
'''

POSITIVE_EXPECTATION_TEMPLATE = '''def before_market(context, parameters):
    """以市值和历史预期回报筛选候选股票。"""
    quantity = int(parameters.get("quantity", 100))
    signals = []
    for symbol in context.universe():
        value = context.factor("market.value", symbol=symbol)
        expected = context.factor("stat.expected-return", symbol=symbol)
        if value and expected["available"] and expected["expected_return"] > 0:
            signals.append({
                "symbol": symbol,
                "action": "buy",
                "quantity": quantity,
                "reason": "正预期回报候选",
            })
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


def runtime_context(source_code: str) -> dict[str, object]:
    dependencies = extract_factor_dependencies(source_code)
    bars = get_container().market_data.list_bars()
    if "daily-bars" in dependencies and not bars:
        raise StateConflictError(
            "策略运行所需日线尚未同步",
            {"recommended_action": "请先前往数据管理同步行情。", "action_url": "/admin/data"},
        )
    prices: dict[str, list[float]] = {}
    for row in sorted(bars, key=lambda item: str(item["trading_day"])):
        prices.setdefault(str(row["symbol"]), []).append(float(str(row["close"])))
    records: dict[str, dict[str, list[dict[str, object]]]] = {}
    for dataset in dependencies - {"daily-bars"}:
        dataset_rows = get_container().market_data.list_records(dataset)
        if not dataset_rows:
            raise StateConflictError(
                f"策略运行依赖的数据集 {dataset} 尚未同步",
                {"dataset": dataset, "action_url": "/admin/data/acquisitions"},
            )
        for row in dataset_rows:
            records.setdefault(dataset, {}).setdefault(str(row.get("symbol", "")), []).append(row)
    return {
        "universe": sorted(prices),
        "prices": prices,
        "market_values": {},
        "records": records,
        "positions": {},
        "current_prices": {},
    }


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
    versions = repository().versions(strategy_id)
    result = SubprocessStrategyRunner().run(
        versions[-1], payload.parameters, runtime_context(versions[-1].source_code)
    )
    record_audit(
        get_container(),
        actor_user_id=g.current_user.id,
        action="run",
        resource_type="strategy",
        resource_id=strategy_id,
        after={"status": result.status.value, "version_id": versions[-1].id},
    )
    return success(
        {
            "id": result.id,
            "status": result.status,
            "signals": [
                {
                    "symbol": signal.symbol,
                    "action": signal.action,
                    "quantity": str(signal.quantity),
                    "reason": signal.reason,
                }
                for signal in result.signals
            ],
            "stdout": result.stdout,
            "error": result.error,
        }
    )


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

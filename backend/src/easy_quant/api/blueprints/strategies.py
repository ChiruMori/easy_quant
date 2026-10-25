from flask import Blueprint, g, request

from easy_quant.api.dependencies import get_container
from easy_quant.api.middleware.auth import require_user
from easy_quant.api.resource_lifecycle import delete_resource, inspect_resource, resource_mutation
from easy_quant.api.responses import success
from easy_quant.api.schemas.strategies import StrategyCreateRequest, StrategyRunRequest
from easy_quant.application.services.audit_runtime import record_audit
from easy_quant.application.services.strategies import StrategyService
from easy_quant.application.services.strategy_validation import PythonStrategyValidator
from easy_quant.infrastructure.core import UuidGenerator

blueprint = Blueprint("strategies", __name__, url_prefix="/api/v1/strategies")


@blueprint.get("/<strategy_id>/deletion-preview")
@require_user
def deletion_preview(strategy_id: str):
    return inspect_resource("strategy", strategy_id)


@blueprint.delete("/<strategy_id>")
@require_user
def delete_strategy(strategy_id: str):
    return delete_resource("strategy", strategy_id)


MOVING_AVERAGE_TEMPLATE = '''def before_market(context, parameters):
    """盘前使用此前已知日线，选择价格站上 5 日均线的股票。"""
    # 每股分配组合权益的 1/预计持股数；10% 指该子仓位的 10%。
    # signal 自动预留预算；实盘未确认建议跨轮继续锁定，回测/快测模拟成交后释放。
    expected_holdings = int(parameters.get("expected_holdings", 10))
    ratio = parameters.get("ratio", "0.10")
    signals = []
    for symbol in context.universe():
        if context.position(symbol) > 0:
            continue
        bars = context.library("market.daily-bars", symbol=symbol)
        ma5 = context.factor("technical.ma", symbol=symbol, window=5)
        if ma5["available"] and bars[-1]["close"] > ma5["value"]:
            signals.append(context.signal(
                symbol, "buy", ratio, "收盘价站上 5 日均线", price=bars[-1]["close"],
                expected_holdings=expected_holdings,
            ))
    return [signal for signal in signals if signal["quantity"] > 0]


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
                expected_holdings=int(parameters.get("expected_holdings", 10)),
            ))
    return [signal for signal in signals if signal["quantity"] > 0]


def after_market(context, parameters):
    """盘后可读取当日收盘数据，本示例只输出运行信息。"""
    return []
'''

GRID_TEMPLATE = """
# 参数示例：{"symbol":"000001","anchor_price":"10","grid_step":"0.05",
#            "base_weight":"0.5","grid_weight":"0.1"}
# 单标的、日线离散网格示范；不保证盈利，不模拟日内多次穿网格。
def before_market(context, parameters):
    return []


def on_market(context, parameters):
    symbol = str(parameters.get("symbol", "000001"))
    anchor = Decimal(str(parameters.get("anchor_price", "10")))
    step = Decimal(str(parameters.get("grid_step", "0.05")))
    base = Decimal(str(parameters.get("base_weight", "0.5")))
    weight = Decimal(str(parameters.get("grid_weight", "0.1")))
    if anchor <= 0 or not 0 < step < 1 or not 0 <= base <= 1 or not 0 < weight <= 1:
        raise ValueError("网格参数无效：锚定价为正，步长与每格仓位在0和1之间")
    price = context.current_price(symbol)
    if price is None or price <= 0:
        return []
    account = context.portfolio()
    # 未确认买入不重复发出；卖出同样由平台扣除锁定股数。
    if symbol in account["pending_buy_symbols"]:
        return []
    held = context.position(symbol)
    equity = account["cash"] + held * price
    if equity <= 0:
        return []
    level = int((anchor - price) / (anchor * step))
    target_weight = max(Decimal(0), min(Decimal(1), base + level * weight))
    target = int(equity * target_weight / price / 100) * 100
    difference = target - held
    if difference >= 100:
        signal = context.signal(symbol, "buy", min(Decimal(1), difference * price / equity),
                                "网格下跌补仓", price=price, expected_holdings=1)
    elif difference <= -100 and held > 0:
        signal = context.signal(symbol, "sell", min(Decimal(1), -difference / held),
                                "网格上涨减仓", price=price, expected_holdings=1)
    else:
        return []
    return [signal] if signal["quantity"] > 0 else []


def after_market(context, parameters):
    return []
"""


def repository():
    return get_container().state.strategies


def strategy_service() -> StrategyService:
    return StrategyService(
        repository(),
        PythonStrategyValidator(),
        get_container().authentication.clock,
        UuidGenerator(),
    )


def serialize(strategy):
    versions = repository().versions(strategy.id)
    current = next((row for row in versions if row.id == strategy.current_version_id), None)
    return {
        "id": strategy.id,
        "name": (current.name or strategy.name) if current else strategy.name,
        "description": strategy.description,
        "current_version_id": strategy.current_version_id,
        "versions": [
            {
                "id": version.id,
                "number": version.number,
                "source_code": version.source_code,
                "created_at": version.created_at.isoformat(),
                "state": version.state.value,
                "name": version.name or strategy.name,
                "description": version.description,
                "revision": version.revision,
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
@resource_mutation
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
    return success(
        {**serialize(strategy), "current_version_id": version.id, "version": version.number},
        status=201,
    )


@blueprint.post("/<strategy_id>/versions")
@require_user
@resource_mutation
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
@resource_mutation
def run_strategy(strategy_id: str):
    from easy_quant.api.blueprints.strategy_workspace import enqueue_quick_test

    payload = StrategyRunRequest.model_validate(request.get_json() or {})
    strategy = repository().get_definition(strategy_id)
    if strategy is None or strategy.owner_id != g.current_user.id:
        return success(None, status=404)
    version_id = payload.strategy_version_id or strategy.current_version_id
    return enqueue_quick_test(payload, strategy_id, version_id)


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
                "timing": job.result_summary.get("timing")
                or job.error_summary.get("details", {}).get("timing"),
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
                "key": "single-symbol-grid",
                "name": "单标的网格策略",
                "source_code": GRID_TEMPLATE,
            },
        ]
    )

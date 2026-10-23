from __future__ import annotations

from flask import Blueprint, g, request

from easy_quant.api.dependencies import get_container
from easy_quant.api.middleware.auth import require_user
from easy_quant.api.resource_lifecycle import resource_mutation
from easy_quant.api.responses import success
from easy_quant.api.schemas.backtests import BacktestCompareRequest, BacktestCreateRequest
from easy_quant.api.strategy_context import strategy_context
from easy_quant.application.services.audit_runtime import record_audit
from easy_quant.application.services.backtest_reporting import stock_performance_page
from easy_quant.domain.scheduling.entities import Job
from easy_quant.domain.shared.errors import ValidationError
from easy_quant.domain.strategies.entities import StrategyState, advanced_strategy_state
from easy_quant.infrastructure.core import UuidGenerator

blueprint = Blueprint("backtests", __name__, url_prefix="/api/v1/backtests")


def _with_job_failure(run):
    # 兼容旧 worker 曾未能保存回测失败状态的记录；读取时不改写历史。
    if run.get("status") not in {"queued", "running"} or not run.get("job_id"):
        return run
    job = get_container().jobs.get(str(run["job_id"]))
    if job is None:
        return {
            **run,
            "status": "failed",
            "progress": 100,
            "error": "回测任务未成功入队，请重新创建回测",
            "error_details": {},
        }
    if job.status.value != "failed" or job.payload.get("backtest_id") != run["id"]:
        return run
    error = job.error_summary
    domain_failure = error.get("code") != "job_failed"
    return {
        **run,
        "status": "failed",
        "progress": 100,
        "error": error.get("message")
        if domain_failure
        else "后台回测任务已失败，请检查 worker 日志并重新创建回测",
        "error_details": error.get("details", {}) if domain_failure else {},
    }


def _find_owned_version(owner_id: str, version_id: str):
    repository = get_container().state.strategies
    version = repository.get_version(version_id)
    definition = repository.get_definition(version.strategy_id) if version is not None else None
    if definition is None or definition.owner_id != owner_id:
        return None
    return version


@blueprint.post("")
@require_user
@resource_mutation
def create_backtest():
    payload = BacktestCreateRequest.model_validate(request.get_json() or {})
    version = _find_owned_version(g.current_user.id, payload.strategy_version_id)
    if version is None:
        return success(None, status=404)
    container = get_container()
    run_id = f"backtest-{UuidGenerator().new()}"
    job_id = f"job-{UuidGenerator().new()}"
    run = {
        "id": run_id,
        "name": payload.name
        or (
            f"{container.state.strategies.get_definition(version.strategy_id).name} · "
            f"v{version.number} · {payload.start_day} 至 {payload.end_day}"
        ),
        "job_id": job_id,
        "owner_id": g.current_user.id,
        "strategy_version_id": payload.strategy_version_id,
        "snapshot_id": "0" * 64,
        "application_version": "0.1.0",
        "created_at": container.authentication.clock.now().isoformat(),
        "status": "queued",
        "progress": 0,
        "config": payload.model_dump(mode="json"),
        "metrics": {},
        "periods": [],
        "trades": [],
        "assumptions": {
            "frequency": "daily",
            "fee_rate": str(payload.fee_rate),
            "slippage_rate": str(payload.slippage_rate),
        },
        "strategy_outputs": [],
    }
    container.backtests.create_with_job(
        run,
        Job(
            job_id,
            "backtest.run",
            f"backtest:{run_id}",
            {"backtest_id": run_id, "owner_id": g.current_user.id},
            container.authentication.clock.now(),
        ),
        container.jobs,
        container.state.strategies,
    )
    record_audit(
        container,
        actor_user_id=g.current_user.id,
        action="enqueue",
        resource_type="backtest",
        resource_id=run_id,
        before={"strategy_state": version.state.value},
        after={
            "status": "queued",
            "job_id": job_id,
            "strategy_version_id": version.id,
            "strategy_state": advanced_strategy_state(version.state, StrategyState.TESTING).value,
        },
    )
    return success(run, status=202)


@blueprint.get("")
@require_user
def list_backtests():
    rows = [
        _with_job_failure(run)
        for run in get_container().backtests.list_for_owner(g.current_user.id)
    ]
    return success(sorted(rows, key=lambda item: str(item["created_at"]), reverse=True))


@blueprint.get("/<run_id>")
@require_user
def get_backtest(run_id: str):
    run = get_container().backtests.get(run_id)
    if run is None or run["owner_id"] != g.current_user.id:
        return success(None, status=404)
    return success(
        {
            **_with_job_failure(run),
            "strategy": strategy_context(
                get_container(), g.current_user.id, str(run.get("strategy_version_id", ""))
            ),
        }
    )


@blueprint.get("/<run_id>/stock-performance")
@require_user
def stock_performance(run_id: str):
    try:
        page = int(request.args.get("page", 1))
        size = int(request.args.get("page_size", 20))
    except ValueError as error:
        raise ValidationError("分页参数必须为整数") from error
    if page < 1 or not 1 <= size <= 100:
        raise ValidationError("页码必须为正数，每页 1–100 条")
    return success(stock_performance_page(get_container(), run_id, g.current_user.id, page, size))


@blueprint.post("/compare")
@require_user
def compare_backtests():
    payload = BacktestCompareRequest.model_validate(request.get_json() or {})
    rows = []
    for run_id in payload.run_ids:
        run = get_container().backtests.get(run_id)
        if run is not None and run["owner_id"] == g.current_user.id:
            rows.append(run)
    return success({"runs": rows})

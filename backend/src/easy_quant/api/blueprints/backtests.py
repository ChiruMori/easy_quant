from __future__ import annotations

from flask import Blueprint, g, request

from easy_quant.api.dependencies import get_container
from easy_quant.api.middleware.auth import require_user
from easy_quant.api.responses import success
from easy_quant.api.schemas.backtests import BacktestCompareRequest, BacktestCreateRequest
from easy_quant.application.services.audit_runtime import record_audit
from easy_quant.domain.scheduling.entities import Job
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
    definition = next(
        (
            item
            for item in repository.definitions.values()
            if item.owner_id == owner_id
            and any(version.id == version_id for version in repository.versions(item.id))
        ),
        None,
    )
    if definition is None:
        return None
    return next(
        (item for item in repository.versions(definition.id) if item.id == version_id), None
    )


@blueprint.post("")
@require_user
def create_backtest():
    payload = BacktestCreateRequest.model_validate(request.get_json() or {})
    if _find_owned_version(g.current_user.id, payload.strategy_version_id) is None:
        return success(None, status=404)
    container = get_container()
    run_id = f"backtest-{UuidGenerator().new()}"
    job_id = f"job-{UuidGenerator().new()}"
    run = {
        "id": run_id,
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
    )
    record_audit(
        container,
        actor_user_id=g.current_user.id,
        action="enqueue",
        resource_type="backtest",
        resource_id=run_id,
        after={"status": "queued", "job_id": job_id},
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
    return success(_with_job_failure(run))


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

import hashlib
from dataclasses import replace

from flask import Blueprint, g, request

from easy_quant.api.blueprints.strategies import strategy_service
from easy_quant.api.dependencies import get_container
from easy_quant.api.middleware.auth import require_user
from easy_quant.api.resource_lifecycle import delete_resource, inspect_resource, resource_mutation
from easy_quant.api.responses import success
from easy_quant.api.schemas.strategies import DraftUpdateRequest, StrategyRunRequest
from easy_quant.application.services.audit_runtime import record_audit
from easy_quant.application.services.strategy_validation import PythonStrategyValidator
from easy_quant.domain.scheduling.entities import Job
from easy_quant.domain.shared.errors import NotFoundError, StateConflictError, ValidationError
from easy_quant.domain.strategies.entities import StrategyState, advanced_strategy_state
from easy_quant.infrastructure.core import UuidGenerator

blueprint = Blueprint("strategy_workspace", __name__, url_prefix="/api/v1/strategies")


def owned_version(strategy_id, version_id):
    container = get_container()
    repository = container.state.strategies
    definition = repository.get_definition(strategy_id)
    version = repository.get_version(version_id)
    if (
        definition is None
        or definition.owner_id != g.current_user.id
        or version is None
        or version.strategy_id != strategy_id
    ):
        raise NotFoundError("strategy_version")
    state = version.state
    if container.backtests.has_for_version(version_id):
        state = advanced_strategy_state(state, StrategyState.TESTING)
    if any(
        row["strategy_version_id"] == version_id for row in container.state.live_instances.values()
    ):
        state = StrategyState.LIVE
    return definition, replace(version, state=state)


def present_version(definition, version):
    return {
        "id": definition.id,
        "version_id": version.id,
        "name": version.name or definition.name,
        "description": version.description,
        "number": version.number,
        "created_at": version.created_at.isoformat(),
        "source_code": version.source_code,
        "state": version.state.value,
        "revision": version.revision,
        "parent_version_id": version.parent_version_id,
        "live_instances": linked_instances(version.id),
    }


def linked_instances(version_id):
    return [
        {"id": row["id"], "name": row.get("name") or row["id"], "status": row["status"]}
        for row in get_container().state.live_instances.values()
        if row["owner_id"] == g.current_user.id and row["strategy_version_id"] == version_id
    ]


@blueprint.get("/workspace")
@require_user
def workspace():
    try:
        page, page_size = (
            int(request.args.get("page", "1")),
            int(request.args.get("page_size", "20")),
        )
    except ValueError as error:
        raise ValidationError("分页参数必须为整数") from error
    state = request.args.get("state", "")
    if page < 1 or not 1 <= page_size <= 100 or state not in {"", "draft", "testing", "live"}:
        raise ValidationError("分页或状态筛选无效")
    rows, total = get_container().state.strategies.page_versions(
        g.current_user.id,
        page,
        page_size,
        request.args.get("search", "").strip(),
        state,
    )
    references = {}
    for instance in get_container().state.live_instances.values():
        if instance["owner_id"] == g.current_user.id:
            references.setdefault(instance["strategy_version_id"], []).append(
                {
                    "id": instance["id"],
                    "name": instance.get("name") or instance["id"],
                    "status": instance["status"],
                }
            )
    return success(
        {
            "items": [
                {
                    **row,
                    "live_instances": references.get(row["version_id"], []),
                    "state": "live" if references.get(row["version_id"]) else row["state"],
                }
                for row in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@blueprint.get("/<strategy_id>/versions/<version_id>")
@require_user
def version_detail(strategy_id, version_id):
    return success(present_version(*owned_version(strategy_id, version_id)))


@blueprint.put("/<strategy_id>/versions/<version_id>")
@require_user
@resource_mutation
def update_draft(strategy_id, version_id):
    definition, version = owned_version(strategy_id, version_id)
    payload = DraftUpdateRequest.model_validate(request.get_json() or {})
    updated = strategy_service().save_draft(
        version,
        payload.name.strip(),
        payload.description,
        payload.source_code,
        payload.expected_revision,
    )
    record_audit(
        get_container(),
        actor_user_id=g.current_user.id,
        action="save_draft",
        resource_type="strategy_version",
        resource_id=version_id,
        before={"revision": version.revision},
        after={"revision": updated.revision},
    )
    return success(present_version(definition, updated))


@blueprint.post("/<strategy_id>/versions/<version_id>/fork")
@require_user
@resource_mutation
def fork_version(strategy_id, version_id):
    definition, version = owned_version(strategy_id, version_id)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or payload.get("confirmed") is not True:
        raise StateConflictError("请确认将从此版本创建新的草稿，原版本保持不变")
    # 也保存旧版本的提升状态，删除关联记录后不得重新变为可编辑状态。
    get_container().state.strategies.advance_state(version_id, version.state)
    created = strategy_service().add_version(
        strategy_id,
        version.source_code,
        parent_version_id=version.id,
        name=version.name or definition.name,
        description=version.description,
    )
    record_audit(
        get_container(),
        actor_user_id=g.current_user.id,
        action="fork_draft",
        resource_type="strategy_version",
        resource_id=created.id,
        before={"parent_version_id": version.id},
        after={"state": "draft", "number": created.number},
    )
    return success(present_version(definition, created), status=201)


@blueprint.get("/<strategy_id>/versions/<version_id>/deletion-preview")
@require_user
def preview_version_deletion(strategy_id, version_id):
    owned_version(strategy_id, version_id)
    return inspect_resource("strategy_version", version_id)


@blueprint.delete("/<strategy_id>/versions/<version_id>")
@require_user
def delete_version(strategy_id, version_id):
    owned_version(strategy_id, version_id)
    return delete_resource("strategy_version", version_id)


def enqueue_quick_test(payload, strategy_id="", version_id=""):
    source = payload.source_code
    if version_id:
        _, version = owned_version(strategy_id, version_id)
        source = source if source is not None else version.source_code
    if source is None:
        raise ValidationError("请提供当前编辑器代码")
    PythonStrategyValidator().validate(source)
    identifier = f"job-{UuidGenerator().new()}"
    container = get_container()
    job = container.jobs.enqueue(
        Job(
            identifier,
            "strategy.run",
            f"strategy-run:{identifier}",
            {
                "owner_id": g.current_user.id,
                "strategy_id": strategy_id,
                "strategy_version_id": version_id,
                "source_code": source,
                "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                "trading_day": payload.trading_day.isoformat(),
                "parameters": payload.parameters,
                "allow_mock": payload.allow_mock,
                "initial_cash": str(payload.initial_cash),
            },
            container.authentication.clock.now(),
        )
    )
    record_audit(
        container,
        actor_user_id=g.current_user.id,
        action="quick_test",
        resource_type="strategy_version",
        resource_id=version_id or identifier,
        after={"job_id": job.id, "source_sha256": job.payload["source_sha256"]},
    )
    return success(present_run(job), status=202)


@blueprint.post("/quick-test")
@require_user
@resource_mutation
def quick_test_editor():
    payload = StrategyRunRequest.model_validate(request.get_json() or {})
    if bool(payload.strategy_id) != bool(payload.strategy_version_id):
        raise ValidationError("策略与版本必须同时指定")
    return enqueue_quick_test(payload, payload.strategy_id or "", payload.strategy_version_id or "")


def present_run(job):
    return {
        "id": job.id,
        "status": job.status.value,
        "strategy_version_id": job.payload.get("strategy_version_id"),
        "trading_day": job.payload.get("trading_day"),
        "code_snapshot_saved": False,
        "source_sha256": job.payload.get("source_sha256"),
        "phase_results": job.result_summary.get("phase_results")
        or job.error_summary.get("details", {}).get("phase_results", []),
        "error": job.error_summary.get("message"),
        "allow_mock": job.payload.get("allow_mock", False),
        "mock_usage": job.result_summary.get("mock_usage", []),
        "portfolio": job.result_summary.get("portfolio"),
        "trades": job.result_summary.get("trades", []),
        "timing": job.result_summary.get("timing")
        or job.error_summary.get("details", {}).get("timing"),
    }


@blueprint.get("/quick-tests/<job_id>")
@require_user
def quick_test_result(job_id):
    job = get_container().jobs.get(job_id)
    if (
        job is None
        or job.job_type != "strategy.run"
        or job.payload.get("owner_id") != g.current_user.id
    ):
        raise NotFoundError("quick_test")
    return success(present_run(job))

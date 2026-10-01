from datetime import UTC, datetime
from decimal import Decimal

from flask import Blueprint, g, request

from easy_quant.api.dependencies import get_container
from easy_quant.api.middleware.auth import require_user
from easy_quant.api.responses import success
from easy_quant.api.schemas.recommendations import RecommendationActionRequest
from easy_quant.application.services.audit_runtime import record_audit
from easy_quant.domain.live_tracking.entities import Recommendation, RecommendationStatus
from easy_quant.domain.live_tracking.ledger import (
    ActualOperation,
    OperationKind,
    PortfolioLedgerEntry,
    entry_for_operation,
    rebuild_portfolio,
)
from easy_quant.infrastructure.core import UuidGenerator

blueprint = Blueprint("recommendations", __name__, url_prefix="/api/v1/recommendations")


def _find_recommendation(recommendation_id: str):
    for instance_id, items in get_container().state.recommendations.items():
        for index, item in enumerate(items):
            if item["id"] == recommendation_id:
                return instance_id, index, item
    return None


def _ledger_entries(live_instance_id: str) -> list[PortfolioLedgerEntry]:
    return [
        PortfolioLedgerEntry(
            str(item["id"]),
            str(item["live_instance_id"]),
            str(item["operation_id"]),
            datetime.fromisoformat(str(item["occurred_at"])),
            Decimal(str(item["cash_delta"])),
            str(item["symbol"]) if item.get("symbol") else None,
            Decimal(str(item["quantity_delta"])),
            Decimal(str(item["price"])),
        )
        for item in get_container().state.portfolio_ledger
        if item["live_instance_id"] == live_instance_id
    ]


@blueprint.post("/<recommendation_id>/<kind>")
@require_user
def act(recommendation_id: str, kind: str):
    found = _find_recommendation(recommendation_id)
    if found is None:
        return success(None, status=404)
    instance_id, index, stored = found
    if stored["owner_id"] != g.current_user.id:
        return success(None, status=404)
    payload = RecommendationActionRequest.model_validate(request.get_json() or {})
    existing = get_container().state.operations.get(payload.idempotency_key)
    if existing is not None:
        return success(existing)
    recommendation = Recommendation(
        str(stored["id"]),
        str(stored["live_instance_id"]),
        str(stored["owner_id"]),
        str(stored["strategy_version_id"]),
        datetime.fromisoformat(str(stored["decision_at"])),
        str(stored["instrument_id"]),
        str(stored["signal_key"]),
        str(stored["action"]),
        str(stored["quantity"]),
        str(stored["reason"]),
        str(stored["business_key"]),
        RecommendationStatus(str(stored["status"])),
        int(stored["version"]),
    )
    if (
        recommendation.version != payload.expected_version
        or recommendation.status is not RecommendationStatus.PENDING
    ):
        return success(None, status=409)
    operation_kind = OperationKind(kind)
    symbol = (
        recommendation.instrument_id if operation_kind is OperationKind.CONFIRM else payload.symbol
    )
    action = recommendation.action if operation_kind is OperationKind.CONFIRM else payload.action
    quantity = (
        Decimal(recommendation.quantity)
        if operation_kind is OperationKind.CONFIRM
        else payload.quantity
    )
    price = payload.price
    if operation_kind is OperationKind.CONFIRM and price <= 0:
        price = Decimal(str(stored.get("suggested_price") or "0"))
    operation = ActualOperation(
        f"operation-{UuidGenerator().new()}",
        recommendation.id,
        recommendation.owner_id,
        operation_kind,
        payload.idempotency_key,
        datetime.now(UTC),
        symbol,
        action,
        quantity,
        price,
        payload.fee,
    )
    entry = entry_for_operation(f"ledger-{UuidGenerator().new()}", instance_id, operation)
    recommendation.status = {
        OperationKind.CONFIRM: RecommendationStatus.CONFIRMED,
        OperationKind.REJECT: RecommendationStatus.REJECTED,
        OperationKind.CORRECT: RecommendationStatus.CORRECTED,
    }[operation_kind]
    recommendation.version += 1
    operation_row = {
        "id": operation.id,
        "kind": operation.kind.value,
        "recommendation_id": recommendation.id,
        "idempotency_key": operation.idempotency_key,
        "occurred_at": operation.occurred_at.isoformat(),
    }
    get_container().state.operations[payload.idempotency_key] = operation_row
    if entry is not None:
        get_container().state.portfolio_ledger.append(
            {
                "id": entry.id,
                "live_instance_id": entry.live_instance_id,
                "operation_id": entry.operation_id,
                "occurred_at": entry.occurred_at.isoformat(),
                "cash_delta": str(entry.cash_delta),
                "symbol": entry.symbol,
                "quantity_delta": str(entry.quantity_delta),
                "price": str(entry.price),
            }
        )
    stored.update(status=recommendation.status.value, version=recommendation.version)
    items = list(get_container().state.recommendations[instance_id])
    items[index] = stored
    get_container().state.recommendations[instance_id] = items
    instance = get_container().state.live_instances[instance_id]
    portfolio_state = rebuild_portfolio(
        Decimal(str(instance.get("initial_cash", "100000"))), _ledger_entries(instance_id)
    )
    instance["positions"] = {key: str(value) for key, value in portfolio_state.positions.items()}
    get_container().state.live_instances[instance_id] = instance
    record_audit(
        get_container(),
        actor_user_id=g.current_user.id,
        action=operation.kind.value,
        resource_type="recommendation",
        resource_id=recommendation.id,
        before={"status": "pending"},
        after={"status": recommendation.status.value, "operation_id": operation.id},
    )
    return success(
        {
            "id": operation.id,
            "kind": operation.kind,
            "recommendation_status": recommendation.status,
            "version": recommendation.version,
        }
    )


@blueprint.get("/portfolio/<live_instance_id>")
@require_user
def portfolio(live_instance_id: str):
    instance = get_container().state.live_instances.get(live_instance_id)
    if instance is None or instance["owner_id"] != g.current_user.id:
        return success(None, status=404)
    state = rebuild_portfolio(
        Decimal(str(instance.get("initial_cash", "100000"))),
        _ledger_entries(live_instance_id),
    )
    return success(
        {
            "cash": str(state.cash),
            "positions": {key: str(value) for key, value in state.positions.items()},
            "costs": {key: str(value) for key, value in state.costs.items()},
            "ledger": [
                {
                    "id": entry.id,
                    "cash_delta": str(entry.cash_delta),
                    "symbol": entry.symbol,
                    "quantity_delta": str(entry.quantity_delta),
                }
                for entry in _ledger_entries(live_instance_id)
            ],
        }
    )

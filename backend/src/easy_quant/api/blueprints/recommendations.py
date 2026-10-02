from flask import Blueprint, g, request

from easy_quant.api.dependencies import get_container
from easy_quant.api.middleware.auth import require_user
from easy_quant.api.responses import success
from easy_quant.api.schemas.recommendations import RecommendationActionRequest
from easy_quant.application.services.recommendation_actions import (
    ActionCommand,
    RecommendationActionService,
    actual_portfolio,
    ledger_entries,
)
from easy_quant.domain.live_tracking.ledger import OperationKind
from easy_quant.domain.shared.errors import NotFoundError, ValidationError
from easy_quant.infrastructure.core import UuidGenerator

blueprint = Blueprint("recommendations", __name__, url_prefix="/api/v1/recommendations")


@blueprint.post("/<recommendation_id>/<kind>")
@require_user
def act(recommendation_id: str, kind: str):
    try:
        operation_kind = OperationKind(kind)
    except ValueError as error:
        raise ValidationError("未知建议处理动作") from error
    payload = RecommendationActionRequest.model_validate(request.get_json() or {})
    container = get_container()
    service = RecommendationActionService(
        container.live_tracking,
        container.authentication.clock,
        UuidGenerator(),
    )
    return success(
        service.apply(
            recommendation_id,
            g.current_user.id,
            ActionCommand(
                operation_kind,
                payload.idempotency_key,
                payload.expected_version,
                payload.symbol,
                payload.action,
                payload.quantity,
                payload.price,
                payload.fee,
            ),
        )
    )


@blueprint.get("/portfolio/<live_instance_id>")
@require_user
def portfolio(live_instance_id: str):
    with get_container().live_tracking.transaction() as state:
        instance = state.instances.get(live_instance_id)
        if instance is None or instance["owner_id"] != g.current_user.id:
            raise NotFoundError("live_instance")
        portfolio_state = actual_portfolio(state, live_instance_id)
        return success(
            {
                "cash": str(portfolio_state.cash),
                "positions": {key: str(value) for key, value in portfolio_state.positions.items()},
                "costs": {key: str(value) for key, value in portfolio_state.costs.items()},
                "ledger": [
                    {
                        "id": entry.id,
                        "cash_delta": str(entry.cash_delta),
                        "symbol": entry.symbol,
                        "quantity_delta": str(entry.quantity_delta),
                    }
                    for entry in ledger_entries(state, live_instance_id)
                ],
            }
        )

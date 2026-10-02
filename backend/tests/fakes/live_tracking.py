from decimal import Decimal

from tests.fakes.platform import make_test_container


def seed_live(container, owner_id="u", instance_id="l", *, initial_cash="1000"):
    container.state.live_instances[instance_id] = {
        "id": instance_id,
        "owner_id": owner_id,
        "status": "active",
        "initial_cash": initial_cash,
        "strategy_version_id": "v",
        "positions": {},
    }
    container.state.recommendations[instance_id] = []


def seed_recommendation(
    container,
    recommendation_id="r",
    owner_id="u",
    instance_id="l",
    *,
    action="buy",
    quantity="10",
    price="10",
):
    row = {
        "id": recommendation_id,
        "live_instance_id": instance_id,
        "owner_id": owner_id,
        "strategy_version_id": "v",
        "decision_at": container.authentication.clock.now().isoformat(),
        "instrument_id": "000001",
        "signal_key": "s",
        "action": action,
        "quantity": quantity,
        "suggested_price": price,
        "reason": "reason",
        "business_key": f"key-{recommendation_id}",
        "status": "pending",
        "version": 0,
    }
    container.state.recommendations[instance_id].append(row)
    return row


def action_container(*, cash: Decimal = Decimal(1000)):
    container = make_test_container()
    seed_live(container, initial_cash=str(cash))
    seed_recommendation(container)
    return container

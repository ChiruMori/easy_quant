from decimal import Decimal

import pytest

from easy_quant.application.services.notification_runtime import notify_owner
from easy_quant.application.services.recommendation_actions import actual_portfolio
from easy_quant.domain.strategies.entities import StrategyDefinition, StrategyVersion
from tests.api.test_strategy_library import authenticated
from tests.fakes.platform import make_test_container


def setup():
    container = make_test_container(initialize_admin=True)
    client, headers = authenticated(container)
    owner = container.authentication.repository.get_user_by_username("admin")
    assert owner
    assert container.secret_box is not None
    container.state.strategies.add_definition(StrategyDefinition("s", owner.id, "原策略", "说明"))
    for number in (1, 2):
        container.state.strategies.add_version(
            StrategyVersion(
                f"v{number}",
                "s",
                number,
                f"# version {number}",
                "hash",
                container.authentication.clock.now(),
            )
        )
    container.backtests.save(
        {
            "id": "b",
            "owner_id": owner.id,
            "strategy_version_id": "v1",
            "status": "succeeded",
            "config": {"initial_cash": "1000", "parameters": {"quantity": 1}},
        },
        b"",
    )
    for identifier, user, enabled in (
        ("n", owner.id, True),
        ("n2", owner.id, True),
        ("other", "someone", True),
        ("disabled", owner.id, False),
    ):
        container.state.subscriptions.append(
            {
                "id": identifier,
                "owner_id": user,
                "enabled": enabled,
                "channel": "ntfy",
                "name": identifier,
                "destination_encrypted": container.secret_box.encrypt("offline-topic"),
            }
        )
    payload = {
        "backtest_id": "b",
        "name": "实盘一",
        "initial_cash": "2000.25",
        "parameters": {"quantity": 5},
        "subscription_ids": ["n"],
        "positions": {"000001": "100"},
    }
    return container, client, headers, payload


@pytest.mark.parametrize(
    "change",
    [
        {"initial_cash": "0"},
        {"initial_cash": "NaN"},
        {"initial_cash": "Infinity"},
        {"initial_cash": "-1"},
        {"name": " "},
        {"subscription_ids": []},
        {"subscription_ids": ["other"]},
        {"subscription_ids": ["disabled"]},
        {"positions": {"sh000300": "1"}},
        {"positions": {"000001": "-1"}},
    ],
)
def test_invalid_start_has_no_side_effect(change):
    container, client, headers, payload = setup()
    response = client.post("/api/v1/live-instances", headers=headers, json={**payload, **change})
    assert response.status_code in {400, 422}
    assert not container.state.live_instances
    assert not container.state.schedules


def test_start_requires_explicit_cash_and_preserves_independent_configuration():
    container, client, headers, payload = setup()
    assert (
        client.post(
            "/api/v1/live-instances", headers=headers, json={"backtest_id": "b"}
        ).status_code
        == 422
    )
    result = client.post("/api/v1/live-instances", headers=headers, json=payload)
    assert result.status_code == 201
    live = result.get_json()["data"]
    detail = client.get(f"/api/v1/live-instances/{live['id']}").get_json()["data"]
    assert detail["strategy"]["number"] == 1
    assert detail["strategy"]["source_code"] == "# version 1"
    assert detail["notification_channels"][0]["name"] == "n"
    assert detail["initial_cash"] == "2000.25"
    assert detail["parameters"] == {"quantity": 5}
    assert container.backtests.get("b")["config"]["initial_cash"] == "1000"
    assert client.get("/api/v1/backtests/b").get_json()["data"]["strategy"]["number"] == 1
    with container.live_tracking.transaction() as state:
        portfolio = actual_portfolio(state, live["id"])
        assert portfolio.cash == Decimal("2000.25")
        assert portfolio.positions == {"000001": Decimal(100)}


def test_named_subscription_test_is_scoped_and_errors_are_redacted():
    container, client, headers, _ = setup()
    calls = []

    class Channel:
        def send(self, subscription, *_args):
            calls.append(subscription.id)

    container.notification_channels["ntfy"] = Channel()
    assert (
        client.post("/api/v1/notifications/subscriptions/other/test", headers=headers).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/notifications/subscriptions/disabled/test", headers=headers
        ).status_code
        == 400
    )
    result = client.post("/api/v1/notifications/subscriptions/n/test", headers=headers)
    assert result.get_json()["data"]["status"] == "delivered"
    assert calls == ["n"]
    notify_owner(
        container, container.state.subscriptions[0]["owner_id"], "event", "title", "body", ["n"]
    )
    notify_owner(
        container, container.state.subscriptions[0]["owner_id"], "event", "title", "body", ["n"]
    )
    assert calls == ["n", "n"]
    client.patch("/api/v1/notifications/subscriptions/n", headers=headers, json={"name": "新名字"})
    row = client.get("/api/v1/notifications/subscriptions").get_json()["data"][0]
    assert row["name"] == "新名字" and row["enabled"]
    assert "destination_encrypted" not in row

    class Broken:
        def send(self, *_args):
            raise RuntimeError("secret-destination")

    container.notification_channels["ntfy"] = Broken()
    result = client.post("/api/v1/notifications/subscriptions/n/test", headers=headers)
    assert result.get_json()["data"]["status"] == "failed"
    assert "secret-destination" not in str(container.state.deliveries)


def test_mock_start_is_rejected():
    container, client, headers, payload = setup()
    row = container.backtests.get("b")
    row["mock_usage"] = [{"count": 1}]
    container.backtests.save(row, b"")
    assert client.post("/api/v1/live-instances", headers=headers, json=payload).status_code == 400
    assert not container.state.live_instances

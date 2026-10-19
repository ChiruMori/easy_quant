from copy import deepcopy

import pytest

from easy_quant.domain.scheduling.entities import Job, JobStatus
from tests.api.test_strategies import _client_and_container, _create_strategy

SOURCE = (
    "def before_market(context, parameters):\n return []\n"
    "def on_market(context, parameters):\n return []\n"
    "def after_market(context, parameters):\n return []"
)


def setup_graph():
    client, container, headers = _client_and_container()
    strategy = _create_strategy(client, headers, SOURCE)
    owner = container.state.strategies.get_definition(strategy["id"]).owner_id
    version = strategy["versions"][0]["id"]
    container.backtests.rows["bt"] = {"id": "bt", "owner_id": owner, "strategy_version_id": version}
    container.jobs.enqueue(
        Job(
            "quick",
            "strategy.run",
            "quick",
            {"strategy_id": strategy["id"]},
            container.authentication.clock.now(),
        )
    )
    container.jobs.enqueue(
        Job(
            "backtest",
            "backtest.run",
            "backtest",
            {"backtest_id": "bt"},
            container.authentication.clock.now(),
        )
    )
    container.state.live_instances["live"] = {
        "id": "live",
        "name": "我的实盘",
        "owner_id": owner,
        "strategy_version_id": version,
        "backtest_id": "bt",
        "status": "terminated",
        "subscription_ids": ["channel"],
    }
    container.state.subscriptions.append(
        {"id": "channel", "name": "提醒", "owner_id": owner, "channel": "ntfy", "enabled": False}
    )
    return client, container, headers, strategy["id"]


@pytest.mark.parametrize("status", ["active", "paused", "terminated"])
def test_any_live_reference_blocks_strategy_deletion(status):
    client, container, headers, strategy_id = setup_graph()
    container.state.live_instances["live"]["status"] = status
    response = client.delete(
        f"/api/v1/strategies/{strategy_id}", headers=headers, json={"confirmed": True}
    )
    assert response.status_code == 409
    assert "我的实盘" in response.get_json()["error"]["message"]
    assert container.state.strategies.get_definition(strategy_id) is not None
    assert "bt" in container.backtests.rows


def test_strategy_confirmation_and_business_cascade_preserve_other_resources():
    client, container, headers, strategy_id = setup_graph()
    container.state.live_instances.clear()
    other = _create_strategy(client, headers, SOURCE)
    preview = client.get(f"/api/v1/strategies/{strategy_id}/deletion-preview").get_json()["data"]
    assert (preview["quick_tests"], preview["backtests"], preview["versions"]) == (1, 1, 1)
    path = f"/api/v1/strategies/{strategy_id}"
    assert client.delete(path, headers=headers).status_code == 409
    assert client.delete(path, headers=headers, json={"confirmed": "true"}).status_code == 409
    assert client.delete(path, headers=headers, json=["confirmed"]).status_code == 409
    assert client.delete(path, headers=headers, json={"confirmed": True}).status_code == 200
    assert container.state.strategies.get_definition(strategy_id) is None
    assert container.state.strategies.versions(strategy_id) == ()
    assert container.backtests.rows == {}
    assert container.jobs.list_all() == []
    assert container.state.strategies.get_definition(other["id"]) is not None
    assert container.state.audit_events[-1]["action"] == "delete"
    assert client.delete(path, headers=headers, json={"confirmed": True}).status_code == 404


@pytest.mark.parametrize("status", ["active", "paused"])
def test_live_must_be_terminated(status):
    client, container, headers, _ = setup_graph()
    container.state.live_instances["live"]["status"] = status
    assert (
        client.delete(
            "/api/v1/live-instances/live", headers=headers, json={"confirmed": True}
        ).status_code
        == 409
    )


def seed_live_data(container):
    state = container.state
    state.recommendations.update({"live": [{"id": "rec"}], "other": [{"id": "other-rec"}]})
    state.operations.update(
        {
            "owner:key": {"id": "op", "recommendation_id": "rec"},
            "other": {"id": "other", "recommendation_id": "other-rec"},
        }
    )
    state.portfolio_ledger.extend(
        [
            {"id": "entry", "live_instance_id": "live", "operation_id": "op"},
            {"id": "other", "live_instance_id": "other"},
        ]
    )
    state.schedules.update(
        {
            "s": {"configuration": {"instance_id": "live"}},
            "other": {"configuration": {"instance_id": "other"}},
        }
    )
    state.deliveries.extend(
        [
            {"id": "delivery", "event_id": "rec", "subscription_id": "channel"},
            {"id": "reminder", "event_id": "live:2026-10-01:position-reminder"},
            {"id": "other", "event_id": "other-rec"},
        ]
    )
    for key, payload in [
        ("live-job", {"instance_id": "live"}),
        ("retry", {"delivery_id": "delivery"}),
    ]:
        container.jobs.enqueue(
            Job(key, "live-analysis", key, payload, container.authentication.clock.now())
        )


def test_terminated_live_cascades_all_data_and_then_unblocks_channel_and_strategy():
    client, container, headers, strategy_id = setup_graph()
    seed_live_data(container)
    assert (
        client.delete(
            "/api/v1/live-instances/live", headers=headers, json={"confirmed": True}
        ).status_code
        == 200
    )
    state = container.state
    assert state.live_instances == {}
    assert set(state.recommendations) == {"other"}
    assert set(state.operations) == {"other"}
    assert [row["id"] for row in state.portfolio_ledger] == ["other"]
    assert set(state.schedules) == {"other"}
    assert [row["id"] for row in state.deliveries] == ["other"]
    assert {job.id for job in container.jobs.list_all()} == {"quick", "backtest"}
    assert "bt" in container.backtests.rows
    assert (
        client.delete(
            "/api/v1/notifications/subscriptions/channel", headers=headers, json={"confirmed": True}
        ).status_code
        == 200
    )
    assert (
        client.delete(
            f"/api/v1/strategies/{strategy_id}", headers=headers, json={"confirmed": True}
        ).status_code
        == 200
    )


def test_channel_references_names_legacy_and_enabled_checks():
    client, container, headers, _ = setup_graph()
    path = "/api/v1/notifications/subscriptions/channel"
    response = client.delete(path, headers=headers, json={"confirmed": True})
    assert response.status_code == 409
    assert "我的实盘" in response.get_json()["error"]["message"]
    del container.state.live_instances["live"]["subscription_ids"]
    assert client.get(path + "/deletion-preview").status_code == 409
    container.state.live_instances.clear()
    container.state.subscriptions[0]["enabled"] = True
    assert client.delete(path, headers=headers, json={"confirmed": True}).status_code == 409


def test_running_retry_rolls_back_entire_live_deletion():
    client, container, headers, _ = setup_graph()
    seed_live_data(container)
    container.jobs.items["retry"].status = JobStatus.RUNNING
    before = deepcopy(container.state)
    response = client.delete(
        "/api/v1/live-instances/live", headers=headers, json={"confirmed": True}
    )
    assert response.status_code == 409
    assert container.state.live_instances == before.live_instances
    assert container.state.recommendations == before.recommendations
    assert container.state.operations == before.operations
    assert container.state.portfolio_ledger == before.portfolio_ledger
    assert container.state.deliveries == before.deliveries


@pytest.mark.parametrize(
    "resource", ["strategies", "live-instances", "notifications/subscriptions"]
)
def test_owner_is_checked_before_returning_association_names(resource):
    client, container, headers, strategy_id = setup_graph()
    if resource == "strategies":
        container.state.strategies.definitions[strategy_id].owner_id = "someone-else"
        identifier = strategy_id
    elif resource == "live-instances":
        container.state.live_instances["live"]["owner_id"] = "someone-else"
        identifier = "live"
    else:
        container.state.subscriptions[0]["owner_id"] = "someone-else"
        identifier = "channel"
    path = f"/api/v1/{resource}/{identifier}"
    assert client.get(path + "/deletion-preview").status_code == 404
    assert client.delete(path, headers=headers, json={"confirmed": True}).status_code == 404


def test_running_quick_test_blocks_strategy_delete():
    client, container, headers, strategy_id = setup_graph()
    container.state.live_instances.clear()
    container.jobs.items["quick"].status = JobStatus.RUNNING
    assert (
        client.delete(
            f"/api/v1/strategies/{strategy_id}", headers=headers, json={"confirmed": True}
        ).status_code
        == 409
    )
    assert "bt" in container.backtests.rows

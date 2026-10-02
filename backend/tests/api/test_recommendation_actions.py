from copy import deepcopy

import pytest

from easy_quant.api.app import create_app
from tests.fakes.live_tracking import seed_live, seed_recommendation
from tests.fakes.platform import make_test_container


@pytest.fixture
def api():
    container = make_test_container(initialize_admin=True)
    client = create_app(settings=container.settings, container=container).test_client()
    login = client.post(
        "/api/v1/auth/login",
        json={
            "username": "admin",
            "password": container.settings.initial_admin_password.get_secret_value(),
        },
    )
    owner = login.get_json()["data"]["user"]["id"]
    seed_live(container, owner)
    seed_recommendation(container, owner_id=owner)
    return container, client, {"X-CSRF-Token": login.get_json()["data"]["csrf_token"]}


def post(client, headers, *, kind="confirm", recommendation="r", key="request-key", **fields):
    return client.post(
        f"/api/v1/recommendations/{recommendation}/{kind}",
        json={"idempotency_key": key, "expected_version": 0, **fields},
        headers=headers,
    )


def test_real_api_conflict_leaves_all_state_unchanged_then_retry_succeeds(api):
    container, client, headers = api
    container.state.live_instances["l"]["initial_cash"] = "10"
    before = deepcopy(container.state)
    response = post(client, headers)
    assert response.status_code == 409
    assert container.state.live_instances == before.live_instances
    assert container.state.recommendations == before.recommendations
    assert container.state.operations == {} and container.state.portfolio_ledger == []
    assert container.state.audit_events == before.audit_events
    response = post(
        client, headers, kind="correct", symbol="000001", action="buy", quantity="1", price="10"
    )
    assert response.status_code == 200
    data = client.get("/api/v1/recommendations/portfolio/l").get_json()["data"]
    assert data["cash"] == "0" and data["positions"] == {"000001": "1"}


def test_real_api_idempotency_response_precision_and_changed_request_conflict(api):
    container, client, headers = api
    first = post(client, headers, fee="0.13")
    assert first.status_code == 200
    for _ in range(10):
        repeated = post(client, headers, fee="0.130")
        assert (
            repeated.status_code == 200 and repeated.get_json()["data"] == first.get_json()["data"]
        )
    assert post(client, headers, fee="0.14").status_code == 409
    assert post(client, headers, key="other-key").status_code == 409
    data = client.get("/api/v1/recommendations/portfolio/l").get_json()["data"]
    assert data["cash"] == "899.87" and len(data["ledger"]) == 1
    assert len(container.state.audit_events) == 1


@pytest.mark.parametrize("fields", [{"price": "NaN"}, {"fee": "-1"}, {"quantity": "Infinity"}])
def test_invalid_decimal_fields_never_write(api, fields):
    container, client, headers = api
    assert post(client, headers, **fields).status_code == 422
    assert container.state.operations == {} and container.state.portfolio_ledger == []


def test_security_and_unknown_kind(api):
    container, client, headers = api
    assert post(client, {}, kind="reject").status_code == 400
    assert post(client, headers, kind="unknown").status_code == 400
    owner = container.state.live_instances["l"]["owner_id"]
    seed_live(container, "other", "other-live")
    seed_recommendation(container, "other-r", "other", "other-live")
    assert post(client, headers, recommendation="other-r").status_code == 404
    assert client.get("/api/v1/recommendations/portfolio/other-live").status_code == 404
    assert container.state.live_instances["l"]["owner_id"] == owner
    client.post("/api/v1/auth/logout", headers=headers)
    assert post(client, headers).status_code == 401


def test_pause_keeps_committed_portfolio_and_audit(api):
    container, client, headers = api
    assert post(client, headers).status_code == 200
    response = client.post("/api/v1/live-instances/l/pause", headers=headers)
    assert response.status_code == 200
    assert response.get_json()["data"]["positions"] == {"000001": "10"}
    assert container.state.live_instances["l"]["cash"] == "900"
    assert container.state.live_instances["l"]["status"] == "paused"
    assert [row["action"] for row in container.state.audit_events] == ["confirm", "pause"]

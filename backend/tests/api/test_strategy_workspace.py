from unittest.mock import patch

import pytest

from easy_quant.application.services.strategies import StrategyService
from easy_quant.application.services.strategy_validation import PythonStrategyValidator
from easy_quant.domain.shared.errors import StateConflictError
from easy_quant.domain.strategies.entities import StrategyState
from easy_quant.infrastructure.core import UuidGenerator
from tests.api.test_resource_lifecycle import SOURCE
from tests.api.test_strategies import _client_and_container, _create_strategy, _run_worker_once


def draft():
    client, container, headers = _client_and_container()
    strategy = _create_strategy(client, headers, SOURCE)
    identifier, version_id = strategy["id"], strategy["current_version_id"]
    return client, container, headers, identifier, version_id


def edit(client, headers, path, source=SOURCE, revision=0):
    return client.put(
        path,
        headers=headers,
        json={
            "name": "修改后的名称",
            "description": "修改说明",
            "source_code": source,
            "expected_revision": revision,
        },
    )


def backtest(client, headers, version_id):
    return client.post(
        "/api/v1/backtests",
        headers=headers,
        json={
            "strategy_version_id": version_id,
            "start_day": "2026-01-01",
            "end_day": "2026-01-31",
            "initial_cash": "100000",
        },
    )


def test_draft_updates_in_place_and_rejects_stale_editor():
    client, container, headers, identifier, version_id = draft()
    path = f"/api/v1/strategies/{identifier}/versions/{version_id}"
    before = client.get(path).get_json()["data"]
    assert before["state"] == "draft"
    changed = SOURCE.replace("return []", "return list()")
    response = edit(client, headers, path, changed)
    assert response.status_code == 200
    updated = response.get_json()["data"]
    assert updated["version_id"] == version_id
    assert updated["revision"] == 1
    assert updated["created_at"] == before["created_at"]
    assert updated["state"] == "draft"
    assert len(container.state.strategies.versions(identifier)) == 1
    assert edit(client, headers, path).status_code == 409
    assert container.state.strategies.get_version(version_id).source_code == changed


def test_backtest_locks_version_even_after_failure_or_deleted_reference():
    client, container, headers, identifier, version_id = draft()
    path = f"/api/v1/strategies/{identifier}/versions/{version_id}"
    stale = container.state.strategies.get_version(version_id)
    submitted = backtest(client, headers, version_id)
    assert submitted.status_code == 202
    assert container.state.strategies.get_version(version_id).state == StrategyState.TESTING
    container.backtests.rows.clear()
    assert edit(client, headers, path).status_code == 409
    service = StrategyService(
        container.state.strategies,
        PythonStrategyValidator(),
        container.authentication.clock,
        UuidGenerator(),
    )
    with pytest.raises(StateConflictError):
        service.save_draft(stale, "stale", "", SOURCE, 0)
    assert container.state.strategies.get_version(version_id).source_code == SOURCE


def test_failed_backtest_submission_does_not_lock_draft():
    client, container, headers, identifier, version_id = draft()
    with patch.object(container.jobs, "enqueue", side_effect=RuntimeError("queue failed")):
        assert backtest(client, headers, version_id).status_code == 500
    assert container.state.strategies.get_version(version_id).state == StrategyState.DRAFT
    assert container.backtests.rows == {}


def test_live_promotes_state_monotonically_and_forks_original_version():
    client, container, headers, identifier, version_id = draft()
    run = backtest(client, headers, version_id).get_json()["data"]
    container.backtests.rows[run["id"]]["status"] = "succeeded"
    container.state.subscriptions.append(
        {
            "id": "channel",
            "name": "提醒",
            "channel": "ntfy",
            "enabled": True,
            "owner_id": container.state.strategies.get_definition(identifier).owner_id,
        }
    )
    started = client.post(
        "/api/v1/live-instances",
        headers=headers,
        json={
            "backtest_id": run["id"],
            "name": "状态验证实盘",
            "subscription_ids": ["channel"],
            "initial_cash": "100000",
        },
    )
    assert started.status_code == 201
    assert container.state.strategies.get_version(version_id).state == StrategyState.LIVE
    live_id = started.get_json()["data"]["id"]
    assert (
        client.post(f"/api/v1/live-instances/{live_id}/terminate", headers=headers).status_code
        == 200
    )
    assert (
        client.delete(
            f"/api/v1/live-instances/{live_id}", headers=headers, json={"confirmed": True}
        ).status_code
        == 200
    )
    path = f"/api/v1/strategies/{identifier}/versions/{version_id}"
    assert client.get(path).get_json()["data"]["state"] == "live"
    assert edit(client, headers, path).status_code == 409
    assert client.post(path + "/fork", headers=headers).status_code == 409
    forked = client.post(path + "/fork", headers=headers, json={"confirmed": True}).get_json()[
        "data"
    ]
    assert forked["state"] == "draft" and forked["number"] == 2
    assert forked["parent_version_id"] == version_id
    assert forked["source_code"] == SOURCE
    assert (
        edit(
            client,
            headers,
            f"/api/v1/strategies/{identifier}/versions/{forked['version_id']}",
            SOURCE.replace("return []", "return list()"),
        ).status_code
        == 200
    )
    assert container.state.strategies.get_version(version_id).source_code == SOURCE
    # 从旧版本复制时，必须使用指定版本的内容，而非最新草稿。
    third = client.post(path + "/fork", headers=headers, json={"confirmed": True}).get_json()[
        "data"
    ]
    assert third["source_code"] == SOURCE and third["number"] == 3


def test_version_delete_preserves_siblings_and_never_reuses_number():
    client, container, headers, identifier, version_id = draft()
    root = f"/api/v1/strategies/{identifier}/versions/{version_id}"
    second = client.post(root + "/fork", headers=headers, json={"confirmed": True}).get_json()[
        "data"
    ]
    second_path = f"/api/v1/strategies/{identifier}/versions/{second['version_id']}"
    assert client.delete(second_path, headers=headers, json={"confirmed": True}).status_code == 200
    assert container.state.strategies.get_version(version_id) is not None
    assert container.state.strategies.get_definition(identifier).current_version_id == version_id
    third = client.post(root + "/fork", headers=headers, json={"confirmed": True}).get_json()[
        "data"
    ]
    assert third["number"] == 3


@pytest.mark.parametrize("failed", [False, True])
def test_unsaved_quick_test_creates_no_version_and_erases_temporary_code(failed):
    client, container, headers = _client_and_container()
    response = client.post(
        "/api/v1/strategies/quick-test",
        headers=headers,
        json={"source_code": SOURCE, "trading_day": "2026-09-29"},
    )
    assert response.status_code == 202
    job_id = response.get_json()["data"]["id"]
    assert container.state.strategies.definitions == {}
    assert container.jobs.get(job_id).payload["source_code"] == SOURCE

    def execute(_container, payload, **_kwargs):
        assert payload["source_code"] == SOURCE
        if failed:
            raise StateConflictError("fixture failure")
        return {"phase_results": [], "status": "succeeded"}

    with patch("easy_quant.worker.handlers.strategies.execute_strategy_tick", side_effect=execute):
        _run_worker_once(container)
    job = container.jobs.get(job_id)
    assert job.status.value == ("failed" if failed else "succeeded")
    assert "source_code" not in job.payload
    result = client.get(f"/api/v1/strategies/quick-tests/{job_id}").get_json()["data"]
    assert result["code_snapshot_saved"] is False
    assert "source_code" not in result
    assert container.state.strategies.definitions == {}


def test_queued_quick_test_uses_editor_content_and_leaves_state_and_saved_code_unchanged():
    client, container, headers, identifier, version_id = draft()
    editor_source = SOURCE.replace("return []", "return list()")
    response = client.post(
        "/api/v1/strategies/quick-test",
        headers=headers,
        json={
            "source_code": editor_source,
            "strategy_id": identifier,
            "strategy_version_id": version_id,
            "trading_day": "2026-09-29",
        },
    )
    assert response.status_code == 202

    def execute(_container, payload, **_kwargs):
        assert payload["source_code"] == editor_source
        return {"phase_results": []}

    with patch("easy_quant.worker.handlers.strategies.execute_strategy_tick", side_effect=execute):
        _run_worker_once(container)
    version = container.state.strategies.get_version(version_id)
    assert version.source_code == SOURCE and version.state == StrategyState.DRAFT
    assert len(container.state.strategies.versions(identifier)) == 1


def test_unsaved_editor_runs_in_restricted_subprocess_without_strategy_record():
    client, container, headers = _client_and_container()
    container.market_data.upsert_bars(
        [
            {
                "symbol": "000001",
                "trading_day": "2026-09-29",
                "open": "10",
                "high": "10",
                "low": "10",
                "close": "10",
                "volume": "100",
                "available_at": "2026-09-29T15:00:00+08:00",
            }
        ]
    )
    response = client.post(
        "/api/v1/strategies/quick-test",
        headers=headers,
        json={"source_code": SOURCE, "trading_day": "2026-09-29"},
    )
    assert response.status_code == 202
    _run_worker_once(container)
    job = container.jobs.get(response.get_json()["data"]["id"])
    assert job.status.value == "succeeded", job.error_summary
    assert len(job.result_summary["phase_results"]) == 3
    assert "source_code" not in job.payload
    assert container.state.strategies.definitions == {}


def test_workspace_paginates_versions_and_filters_without_returning_source():
    client, container, headers, identifier, first = draft()
    service = StrategyService(
        container.state.strategies,
        PythonStrategyValidator(),
        container.authentication.clock,
        UuidGenerator(),
    )
    for _ in range(42):
        service.add_version(identifier, SOURCE)
    container.state.strategies.advance_state(first, StrategyState.TESTING)
    pages = [
        client.get(f"/api/v1/strategies/workspace?page={page}").get_json()["data"]
        for page in (1, 2, 3)
    ]
    assert [len(page["items"]) for page in pages] == [20, 20, 3]
    assert all(page["total"] == 43 for page in pages)
    assert len({row["version_id"] for page in pages for row in page["items"]}) == 43
    assert all("source_code" not in row for page in pages for row in page["items"])
    filtered = client.get("/api/v1/strategies/workspace?state=testing").get_json()["data"]
    assert filtered["total"] == 1 and filtered["items"][0]["version_id"] == first
    assert (
        client.get("/api/v1/strategies/workspace?search=missing").get_json()["data"]["total"] == 0
    )


@pytest.mark.parametrize("query", ["page=0", "page=bad", "page_size=101", "state=invalid"])
def test_workspace_validates_pagination(query):
    client, _, _, _, _ = draft()
    assert client.get("/api/v1/strategies/workspace?" + query).status_code == 400


def test_workspace_mutations_enforce_ownership_and_version_pair():
    client, container, headers, identifier, version_id = draft()
    other = _create_strategy(client, headers, SOURCE)
    path = f"/api/v1/strategies/{other['id']}/versions/{version_id}"
    assert client.get(path).status_code == 404
    container.state.strategies.definitions[identifier].owner_id = "other-owner"
    path = f"/api/v1/strategies/{identifier}/versions/{version_id}"
    assert client.get(path).status_code == 404
    assert edit(client, headers, path).status_code == 404
    assert client.post(path + "/fork", headers=headers, json={"confirmed": True}).status_code == 404
    assert client.delete(path, headers=headers, json={"confirmed": True}).status_code == 404
    assert (
        client.post(
            "/api/v1/strategies/quick-test",
            headers=headers,
            json={
                "source_code": SOURCE,
                "strategy_id": identifier,
                "strategy_version_id": version_id,
                "trading_day": "2026-09-29",
            },
        ).status_code
        == 404
    )


def test_live_rejects_missing_strategy_version_even_with_owned_successful_backtest():
    client, container, headers, identifier, version_id = draft()
    owner = container.state.strategies.get_definition(identifier).owner_id
    container.backtests.rows["orphan"] = {
        "id": "orphan",
        "owner_id": owner,
        "strategy_version_id": version_id,
        "status": "succeeded",
    }
    container.state.strategies.version_items[identifier] = []
    response = client.post(
        "/api/v1/live-instances",
        headers=headers,
        json={
            "backtest_id": "orphan",
            "name": "不能创建",
            "initial_cash": "10000",
            "subscription_ids": ["channel"],
        },
    )
    assert response.status_code == 404
    assert container.state.live_instances == {}

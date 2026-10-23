import json
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from sqlalchemy.orm import Session

from easy_quant.api.app import create_app
from easy_quant.domain.scheduling.entities import Job, JobStatus
from easy_quant.infrastructure.persistence.models.runtime_state import RuntimeDocumentModel
from easy_quant.infrastructure.persistence.repositories.runtime_documents import SqlJsonList
from tests.fakes.platform import make_test_container


class FakeKeys:
    def __init__(self, values=None):
        self.values = values if values is not None else ["entry"]

    def all(self) -> list[str]:
        return self.values

    def __iter__(self):
        return iter(self.values)


class FakeDocuments:
    def __init__(self, namespace: str, payload: dict[str, str]) -> None:
        self.row = RuntimeDocumentModel(
            namespace=namespace, key="entry", payload_json=json.dumps(payload)
        )

    def get(self, _model: object, key: tuple[str, str]) -> RuntimeDocumentModel | None:
        return self.rows.get(key)

    @property
    def rows(self):
        if not hasattr(self, "_rows"):
            self._rows = {(self.row.namespace, self.row.key): self.row}
        return self._rows

    def merge(self, row):
        self.rows[row.namespace, row.key] = row

    def commit(self):
        pass

    def scalars(self, statement: Any) -> FakeKeys:
        namespace = statement.compile().params["namespace_1"]
        rows = [row for (ns, _), row in sorted(self.rows.items()) if ns == namespace]
        return FakeKeys(
            [
                row.payload_json
                if statement.selected_columns[0].name == "payload_json"
                else row.key
                for row in rows
            ]
        )


@pytest.mark.parametrize(
    ("endpoint", "attribute"),
    [
        ("/api/v1/admin/market-data/datasets", "datasets"),
        ("/api/v1/admin/jobs", "jobs"),
        ("/api/v1/admin/audit-events", "audit_events"),
    ],
)
def test_persistent_lists_are_serialized_at_the_api_boundary(endpoint, attribute) -> None:
    container = make_test_container(initialize_admin=True)
    container.jobs = None
    payload = {"id": "entry", "key": "daily-bars"}
    documents = FakeDocuments(attribute, payload)
    setattr(container.state, attribute, SqlJsonList(cast(Session, documents), attribute))
    client = create_app(settings=container.settings, container=container).test_client()
    client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "change-this-admin-password"}
    )
    response = client.get(endpoint)
    assert response.status_code == 200
    if attribute == "datasets":
        data = response.get_json()["data"]
        assert data[0] == payload
        assert {row["key"] for row in data} >= {"daily-bars", "trading-calendar", "securities"}
        return
    assert response.get_json()["data"] == (
        {"items": [payload], "total": 1, "page": 1, "page_size": 20}
        if attribute == "jobs"
        else [payload]
    )


def test_request_teardown_releases_the_database_session() -> None:
    class FakeScope:
        removed = 0

        def remove(self) -> None:
            self.removed += 1

    container = make_test_container()
    scope = FakeScope()
    container.database_session = scope
    client = create_app(settings=container.settings, container=container).test_client()
    assert client.get("/api/v1/health").status_code == 200
    assert scope.removed == 1


def test_admin_jobs_reports_expired_lease_without_exposing_payload() -> None:
    container = make_test_container(initialize_admin=True)
    now = datetime(2026, 9, 29, 8, 0, tzinfo=UTC)
    container.jobs.enqueue(
        Job(
            "job-1",
            "strategy.run",
            "strategy-run:1",
            {"secret": "must-not-be-returned"},
            now - timedelta(minutes=10),
            status=JobStatus.RUNNING,
            lease_owner="stopped-worker",
            lease_until=now - timedelta(minutes=1),
        )
    )
    client = create_app(settings=container.settings, container=container).test_client()
    client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "change-this-admin-password"}
    )
    response = client.get("/api/v1/admin/jobs")
    job = response.get_json()["data"]["items"][0]
    assert job["lease_expired"] is True
    assert job["lease_until"] == (now - timedelta(minutes=1)).isoformat()
    assert "must-not-be-returned" not in response.get_data(as_text=True)

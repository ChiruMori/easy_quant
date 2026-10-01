import json
from typing import Any, cast

import pytest
from sqlalchemy.orm import Session

from easy_quant.api.app import create_app
from easy_quant.infrastructure.persistence.models.runtime_state import RuntimeDocumentModel
from easy_quant.infrastructure.persistence.repositories.runtime_documents import SqlJsonList
from tests.fakes.platform import make_test_container


class FakeKeys:
    def all(self) -> list[str]:
        return ["entry"]


class FakeDocuments:
    def __init__(self, namespace: str, payload: dict[str, str]) -> None:
        self.row = RuntimeDocumentModel(
            namespace=namespace, key="entry", payload_json=json.dumps(payload)
        )

    def get(self, _model: object, key: tuple[str, str]) -> RuntimeDocumentModel | None:
        return self.row if key == (self.row.namespace, self.row.key) else None

    def scalars(self, statement: Any) -> FakeKeys:
        assert statement.compile().params["namespace_1"] == self.row.namespace
        return FakeKeys()


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
    assert response.get_json()["data"] == [payload]


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

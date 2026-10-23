import json
from typing import Any, cast

from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session

from easy_quant.infrastructure.persistence.repositories.runtime_documents import SqlJsonList


def test_list_iteration_uses_one_streamed_query_instead_of_per_row_keys():
    class FakeSession:
        calls = []

        def scalars(self, statement):
            self.calls.append(statement)
            return [json.dumps({"id": str(index)}) for index in range(100)]

    session = FakeSession()
    values = SqlJsonList(cast(Session, session), "deliveries")
    assert sum(1 for _ in values) == 100
    assert len(session.calls) == 1
    assert session.calls[0].get_execution_options()["yield_per"] == 500


def test_delivery_page_filters_and_limits_in_database():
    class FakeSession:
        statements: list[Any] = []

        def scalar(self, statement):
            self.statements.append(statement)
            return 25

        def scalars(self, statement):
            self.statements.append(statement)
            return ['{"id":"delivery"}']

    session = FakeSession()
    result = SqlJsonList(cast(Session, session), "deliveries").page_for_live(
        "owner", "live", {"r"}, 2, 20
    )
    assert result["total"] == 25 and result["page"] == 2
    statement = session.statements[1].compile(dialect=mysql.dialect())
    assert "LIMIT" in str(statement) and "json_extract" in str(statement)
    assert "owner" in statement.params.values()
    assert 20 in statement.params.values()


def test_dataset_append_does_not_overwrite_a_numeric_slot_after_deletion():
    class Documents(dict):
        namespace = "datasets"

    documents = Documents(
        {"00000000": {"key": "securities"}, "00000002": {"key": "trading-calendar"}}
    )
    store = SqlJsonList(cast(Session, object()), "datasets")
    store._mapping = cast(Any, documents)
    store.append({"key": "daily-bars"})
    assert documents["00000002"] == {"key": "trading-calendar"}
    assert len(documents) == 3

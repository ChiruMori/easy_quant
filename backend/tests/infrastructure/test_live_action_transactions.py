import json
from contextlib import contextmanager
from copy import deepcopy
from typing import Any, cast

import pytest
from sqlalchemy.dialects import mysql

from easy_quant.application.services.recommendation_actions import (
    ActionCommand,
    RecommendationActionService,
)
from easy_quant.domain.live_tracking.ledger import OperationKind
from easy_quant.domain.shared.errors import StateConflictError
from easy_quant.infrastructure.persistence.models.runtime_state import RuntimeDocumentModel
from easy_quant.infrastructure.persistence.repositories.live_actions import SqlLiveTrackingStore
from tests.fakes.core import SequentialIdGenerator
from tests.fakes.live_tracking import action_container


class Values:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class DocumentDatabase:
    def __init__(self, container):
        self.rows = {}
        for namespace in ("live_instances", "recommendations"):
            for key, value in getattr(container.state, namespace).items():
                self.rows[namespace, key] = json.dumps(value)
        self.commits = self.rollbacks = self.closes = 0
        self.statements = []
        self.fail_namespace = None
        self.fail_commit = False

    def session(self):
        return DocumentSession(self)


class DocumentSession:
    def __init__(self, db):
        self.db = db
        self.rows = deepcopy(db.rows)
        self.pending_namespace = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.db.closes += 1

    @contextmanager
    def begin(self):
        try:
            yield
            if self.db.fail_commit:
                raise RuntimeError("fake commit failure")
            self.db.rows = self.rows
            self.db.commits += 1
        except Exception:
            self.db.rollbacks += 1
            raise

    def execute(self, statement):
        compiled = statement.compile(dialect=mysql.dialect())
        self.db.statements.append(str(compiled))
        assert str(compiled).startswith("INSERT INTO runtime_documents")
        self.rows["live_action_mutex", "singleton"] = "{}"

    def scalar(self, statement):
        sql = str(statement.compile(dialect=mysql.dialect()))
        self.db.statements.append(sql)
        assert "FOR UPDATE" in sql
        return self.get(RuntimeDocumentModel, ("live_action_mutex", "singleton"))

    def get(self, _model, key):
        payload = self.rows.get(key)
        return (
            RuntimeDocumentModel(namespace=key[0], key=key[1], payload_json=payload)
            if payload is not None
            else None
        )

    def merge(self, row):
        self.pending_namespace = row.namespace
        self.rows[row.namespace, row.key] = row.payload_json

    def flush(self):
        if self.pending_namespace == self.db.fail_namespace:
            raise RuntimeError("fake write failure")

    def scalars(self, statement):
        namespace = statement.compile().params["namespace_1"]
        return Values([key for ns, key in self.rows if ns == namespace])

    def commit(self):
        raise AssertionError("JSON adapters must not commit inside the unit of work")


def setup():
    container = action_container()
    db = DocumentDatabase(container)
    store = SqlLiveTrackingStore(cast(Any, db.session))
    actions = RecommendationActionService(
        store, container.authentication.clock, SequentialIdGenerator()
    )
    return db, actions


def test_mysql_mutex_lock_precedes_writes_and_json_adapters_do_not_commit():
    db, actions = setup()
    response = actions.apply("r", "u", ActionCommand(OperationKind.CONFIRM, "request-key", 0))
    assert db.commits == 1 and db.rollbacks == 0 and db.closes == 1
    assert "ON DUPLICATE KEY UPDATE" in db.statements[0]
    assert "FOR UPDATE" in db.statements[1]
    counts = {
        namespace: sum(ns == namespace for ns, _key in db.rows)
        for namespace in ("operations", "portfolio_ledger", "audit_events")
    }
    assert counts == {"operations": 1, "portfolio_ledger": 1, "audit_events": 1}
    rows = json.loads(db.rows["recommendations", "l"])
    assert rows[0]["status"] == "confirmed" and rows[0]["version"] == 1
    assert (
        actions.apply("r", "u", ActionCommand(OperationKind.CONFIRM, "request-key", 0)) == response
    )
    assert len([key for key in db.rows if key[0] == "portfolio_ledger"]) == 1


@pytest.mark.parametrize(
    "stage",
    [
        "operations",
        "portfolio_ledger",
        "recommendations",
        "live_instances",
        "audit_events",
        "commit",
    ],
)
def test_any_sql_write_or_commit_failure_rolls_back_and_closes_session(stage):
    db, actions = setup()
    before = deepcopy(db.rows)
    if stage == "commit":
        db.fail_commit = True
    else:
        db.fail_namespace = stage
    command = ActionCommand(OperationKind.CONFIRM, "request-key", 0)
    with pytest.raises(RuntimeError, match="fake"):
        actions.apply("r", "u", command)
    assert db.rows == before
    assert db.commits == 0 and db.rollbacks == db.closes == 1
    db.fail_commit, db.fail_namespace = False, None
    actions.apply("r", "u", command)
    assert db.commits == 1


def test_invalid_candidate_rolls_back_sql_transaction_before_any_business_write():
    db, actions = setup()
    row = json.loads(db.rows["live_instances", "l"])
    row["initial_cash"] = "1"
    db.rows["live_instances", "l"] = json.dumps(row)
    before = deepcopy(db.rows)
    with pytest.raises(StateConflictError, match="负现金"):
        actions.apply("r", "u", ActionCommand(OperationKind.CONFIRM, "request-key", 0))
    assert db.rows == before and db.commits == 0 and db.rollbacks == 1

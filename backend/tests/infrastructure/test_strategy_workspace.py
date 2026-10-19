from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session

from easy_quant.domain.shared.errors import StateConflictError
from easy_quant.domain.strategies.entities import (
    StrategyState,
    StrategyVersion,
    advanced_strategy_state,
)
from easy_quant.infrastructure.persistence.repositories.strategies import (
    SqlAlchemyStrategyRepository,
)


class DraftSession:
    def __init__(self, affected=1):
        self.affected = affected
        self.statements = []
        self.commits = self.rollbacks = 0

    def execute(self, statement):
        self.statements.append(statement)
        return SimpleNamespace(rowcount=self.affected)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


@pytest.mark.parametrize("affected", [0, 1])
def test_sql_draft_save_has_state_and_revision_guards(affected):
    session = DraftSession(affected)
    repository = SqlAlchemyStrategyRepository(cast(Session, session))
    version = StrategyVersion(
        "v", "s", 1, "source", "hash", datetime(2026, 9, 29, tzinfo=UTC), revision=3
    )
    if affected:
        repository.save_draft(version, 2)
        assert session.commits == 1 and session.rollbacks == 0
    else:
        with pytest.raises(StateConflictError):
            repository.save_draft(version, 2)
        assert session.commits == 0 and session.rollbacks == 1
    statement = session.statements[0]
    sql = str(statement.compile(dialect=mysql.dialect()))
    where = sql.split("WHERE")[1]
    assert "state =" in where and "revision =" in where and "id =" in where
    assert "draft" in statement.compile().params.values()
    assert statement.compile().params["revision_1"] == 2


def test_status_never_regresses_in_domain_or_sql():
    for current in StrategyState:
        for target in StrategyState:
            final = advanced_strategy_state(current, target)
            assert list(StrategyState).index(final) >= list(StrategyState).index(current)
    session = DraftSession()
    SqlAlchemyStrategyRepository.advance_state_in_transaction(session, "v", StrategyState.DRAFT)
    assert session.statements == []
    SqlAlchemyStrategyRepository.advance_state_in_transaction(session, "v", StrategyState.TESTING)
    statement = session.statements[0]
    assert statement.compile().params["state_1"] == ["draft"]


def test_sql_workspace_pagination_projects_metadata_without_source_or_history_payload():
    class PageSession:
        def __init__(self):
            self.statements = []

        def scalar(self, statement):
            self.statements.append(statement)
            return 45

        def execute(self, statement):
            self.statements.append(statement)
            return SimpleNamespace(mappings=lambda: [])

    session = PageSession()
    rows, total = SqlAlchemyStrategyRepository(cast(Session, session)).page_versions(
        "owner", 3, 20, "test%", "testing"
    )
    assert total == 45 and rows == []
    statement = session.statements[1]
    sql = str(statement.compile(dialect=mysql.dialect()))
    assert "source_code" not in sql and "payload_json" not in sql
    assert "LIMIT" in sql and "owner_id" in sql and "ESCAPE" in sql
    assert statement.compile().params["param_1"] == 20
    assert statement.compile().params["param_2"] == 40


@pytest.mark.parametrize("already_present", [False, True])
def test_workspace_migration_preserves_locks_and_backfills_all_live_statuses(
    monkeypatch, already_present
):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).parents[2] / "migrations/versions/0013_strategy_workspace.py"
    spec = importlib.util.spec_from_file_location("workspace_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class Inspector:
        def get_columns(self, table):
            names = (
                (
                    ["state", "name", "description", "revision"]
                    if table == "strategy_versions"
                    else ["next_version_number"]
                )
                if already_present
                else []
            )
            return [{"name": name} for name in names]

    added, statements = [], []
    monkeypatch.setattr(module.op, "get_bind", lambda: object())
    monkeypatch.setattr(module.sa, "inspect", lambda _bind: Inspector())
    monkeypatch.setattr(
        module.op, "add_column", lambda table, column: added.append((table, column))
    )
    monkeypatch.setattr(
        module.op, "execute", lambda sql: statements.append(" ".join(str(sql).split()))
    )
    module.upgrade()
    assert len(added) == (0 if already_present else 5)
    assert all(not column.foreign_keys for _, column in added)
    testing = next(sql for sql in statements if "SET state = 'testing'" in sql)
    assert "WHERE state = 'draft'" in testing and "backtest_runs" in testing
    live = next(sql for sql in statements if "SET state = 'live'" in sql)
    assert "runtime_documents" in live and "live_instances" in live
    assert "status" not in live  # 暂停或终止的实盘同样锁定来源版本。
    assert any("GREATEST" in sql for sql in statements)

import importlib.util
import json
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

import pytest

from easy_quant.application.services.resource_lifecycle import ResourceLifecycleService
from easy_quant.infrastructure.persistence.models.backtesting import (
    BacktestMetricModel,
    BacktestPeriodModel,
    BacktestRunModel,
    DataSnapshotChunkModel,
    DataSnapshotModel,
    SimulatedTradeModel,
)
from easy_quant.infrastructure.persistence.models.runtime_state import RuntimeDocumentModel
from easy_quant.infrastructure.persistence.models.scheduling import JobModel
from easy_quant.infrastructure.persistence.models.strategies import (
    StrategyModel,
    StrategyVersionModel,
)
from easy_quant.infrastructure.persistence.repositories.resource_lifecycle import (
    SqlResourceLifecycleStore,
)


class Database:
    """只模拟事务与语句应用，不连接数据库或本地持久存储。"""

    def __init__(self, shared_snapshot=False):
        self.rows = {
            StrategyModel: [
                StrategyModel(
                    id="s", owner_id="owner", name="策略", description="", current_version_id="v"
                )
            ],
            StrategyVersionModel: [StrategyVersionModel(id="v", strategy_id="s")],
            BacktestRunModel: [
                BacktestRunModel(
                    id="b",
                    owner_id="owner",
                    strategy_version_id="v",
                    snapshot_id="snapshot",
                    payload_json=json.dumps(
                        {"id": "b", "owner_id": "owner", "strategy_version_id": "v"}
                    ),
                )
            ],
            JobModel: [],
            RuntimeDocumentModel: [],
            DataSnapshotModel: [DataSnapshotModel(id="snapshot")],
            DataSnapshotChunkModel: [DataSnapshotChunkModel(snapshot_id="snapshot", sequence=0)],
            BacktestPeriodModel: [BacktestPeriodModel(run_id="b")],
            SimulatedTradeModel: [SimulatedTradeModel(run_id="b")],
            BacktestMetricModel: [BacktestMetricModel(run_id="b")],
        }
        if shared_snapshot:
            self.rows[BacktestRunModel].append(
                BacktestRunModel(
                    id="other",
                    owner_id="other",
                    strategy_version_id="other-v",
                    snapshot_id="snapshot",
                    payload_json=json.dumps(
                        {"id": "other", "owner_id": "other", "strategy_version_id": "other-v"}
                    ),
                )
            )
        self.fail_commit = False
        self.commits = self.rollbacks = 0
        self.statements = []

    def session(self):
        return Session(self)


class Session:
    def __init__(self, database):
        self.db = database
        self.rows = deepcopy(database.rows)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    @contextmanager
    def begin(self):
        try:
            yield
            if self.db.fail_commit:
                raise RuntimeError("commit failed")
            self.db.rows = self.rows
            self.db.commits += 1
        except Exception:
            self.db.rollbacks += 1
            raise

    def scalars(self, statement):
        self.db.statements.append(statement)
        return self.rows[statement.column_descriptions[0]["entity"]]

    def scalar(self, _statement):
        return next(
            (row.id for row in self.rows[BacktestRunModel] if row.snapshot_id == "snapshot"), None
        )

    def delete(self, row):
        self.rows[type(row)].remove(row)

    def add(self, row):
        self.rows.setdefault(type(row), []).append(row)

    def flush(self):
        pass

    def execute(self, statement):
        self.db.statements.append(statement)
        name = statement.table.name
        if name == "resource_lifecycle_mutex":
            return
        model = next(model for model in self.rows if model.__tablename__ == name)
        params = statement.compile().params
        if statement.__visit_name__ == "update":
            for row in self.rows[model]:
                if row.id == params["id_1"] and row.state in params["state_1"]:
                    row.state = params["state"]
            return
        column = str(statement.whereclause.left).split(".")[-1]
        expected = next(iter(params.values()))
        self.rows[model] = [row for row in self.rows[model] if getattr(row, column) != expected]


def service_for(database):
    class StoreWithoutGuard(SqlResourceLifecycleStore):
        @contextmanager
        def guard(self):
            # 单独验证业务事务，互斥锁事务在下方另测。
            yield

    store = StoreWithoutGuard(database.session)
    return ResourceLifecycleService(store)


@pytest.mark.parametrize("shared", [False, True])
def test_sql_cascade_cleans_results_and_only_unreferenced_snapshots(shared):
    database = Database(shared)
    service_for(database).delete(
        "strategy", "s", "owner", True, {"id": "audit", "action": "delete"}
    )
    assert database.commits == 1
    assert database.rows[StrategyModel] == []
    assert database.rows[StrategyVersionModel] == []
    for model in (BacktestPeriodModel, SimulatedTradeModel, BacktestMetricModel):
        assert database.rows[model] == []
    assert len(database.rows[BacktestRunModel]) == int(shared)
    assert len(database.rows[DataSnapshotModel]) == int(shared)
    assert len(database.rows[DataSnapshotChunkModel]) == int(shared)
    assert len(database.rows[RuntimeDocumentModel]) == 1


def test_sql_commit_failure_rolls_back_deletes_and_audit():
    database = Database()
    database.fail_commit = True
    with pytest.raises(RuntimeError, match="commit failed"):
        service_for(database).delete("strategy", "s", "owner", True, {"id": "audit"})
    assert database.commits == 0
    assert database.rollbacks == 1
    assert len(database.rows[StrategyModel]) == 1
    assert len(database.rows[BacktestRunModel]) == 1
    assert len(database.rows[BacktestPeriodModel]) == 1
    assert database.rows[RuntimeDocumentModel] == []


@pytest.mark.parametrize("fail_commit", [False, True])
def test_live_instance_and_live_state_are_committed_atomically(fail_commit):
    database = Database()
    database.rows[StrategyVersionModel][0].state = "draft"
    database.fail_commit = fail_commit
    store = SqlResourceLifecycleStore(database.session)
    instance = {"id": "live", "owner_id": "owner", "strategy_version_id": "v"}
    schedules = [
        {"id": f"plan-{phase}", "configuration": {"instance_id": "live", "phase": phase}}
        for phase in ("before_market", "on_market")
    ]
    if fail_commit:
        with pytest.raises(RuntimeError, match="commit failed"):
            store.add_live_instance(instance, schedules)
        assert database.rows[StrategyVersionModel][0].state == "draft"
        assert database.rows[RuntimeDocumentModel] == []
    else:
        store.add_live_instance(instance, schedules)
        assert database.rows[StrategyVersionModel][0].state == "live"
        assert len(database.rows[RuntimeDocumentModel]) == 3
        assert {r.namespace for r in database.rows[RuntimeDocumentModel]} == {
            "live_instances",
            "schedules",
        }
        assert database.rows[RuntimeDocumentModel][0].key == "live"


def test_resource_guard_uses_transactional_mysql_upsert_lock():
    database = Database()
    store = SqlResourceLifecycleStore(database.session)
    with store.guard():
        assert database.commits == 0
    assert database.commits == 1
    statement = database.statements[0]
    assert "ON DUPLICATE KEY UPDATE" in str(statement)
    assert statement.table.name == "resource_lifecycle_mutex"
    assert statement.compile().params["key"] == "singleton"


def test_constraint_migration_only_removes_deletion_graph_constraints(monkeypatch):
    path = Path(__file__).parents[2] / "migrations/versions/0012_resource_lifecycle_constraints.py"
    spec = importlib.util.spec_from_file_location("lifecycle_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class Inspector:
        def get_table_names(self):
            return ["strategy_versions", "backtest_periods", "actual_operations", "sessions"]

        def get_foreign_keys(self, table):
            targets = {
                "strategy_versions": "strategies",
                "backtest_periods": "backtest_runs",
                "actual_operations": "recommendations",
                "sessions": "users",
            }
            return [{"name": f"fk_{table}", "referred_table": targets[table]}]

    removed = []
    monkeypatch.setattr(module.op, "get_bind", lambda: object())
    monkeypatch.setattr(module.op, "create_table", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module.sa, "inspect", lambda _: Inspector())
    monkeypatch.setattr(
        module.op, "drop_constraint", lambda name, table, **kwargs: removed.append((name, table))
    )
    module.upgrade()
    assert {table for _, table in removed} == {
        "strategy_versions",
        "backtest_periods",
        "actual_operations",
    }

import gzip
import json
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from sqlalchemy.orm import Session

from easy_quant.domain.scheduling.entities import Job
from easy_quant.infrastructure.persistence.models.backtesting import (
    BacktestRunModel,
    DataSnapshotChunkModel,
    DataSnapshotModel,
)
from easy_quant.infrastructure.persistence.models.strategies import StrategyVersionModel
from easy_quant.infrastructure.persistence.repositories.runtime import SqlAlchemyBacktestStore
from easy_quant.infrastructure.persistence.snapshot_spool import SnapshotSpool


class ForeignKeySession:
    """离线模拟无 ORM relationship 时的分表写入与即时外键检查。"""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, tuple[Any, ...]], Any] = {}
        self.pending: list[Any] = []
        self.commits = 0

    def add(self, row: Any) -> None:
        self.pending.append(row)

    def get(self, model: Any, key: str) -> Any:
        self.flush()  # 查询会触发 autoflush。
        return self.rows.get((model.__tablename__, (key,)))

    def flush(self) -> None:
        # 无 relationship 的 mapper 不能依赖外键自动决定父子写入顺序。
        for row in sorted(self.pending, key=lambda item: item.__tablename__):
            table = row.__table__
            for foreign_key in table.foreign_keys:
                target_table = foreign_key.target_fullname.rsplit(".", 1)[0]
                if target_table == "users":
                    continue  # 调用者已通过认证。
                key = getattr(row, foreign_key.parent.name)
                assert (target_table, (key,)) in self.rows, "父记录尚未写入"
            key = tuple(getattr(row, column.name) for column in table.primary_key)
            assert (table.name, key) not in self.rows, "重复写入"
            self.rows[table.name, key] = row
        self.pending.clear()

    def execute(self, statement: Any) -> None:
        self.flush()
        run_id = statement.compile().params["run_id_1"]
        self.rows = {
            key: row
            for key, row in self.rows.items()
            if not (key[0] == statement.table.name and row.run_id == run_id)
        }

    def commit(self) -> None:
        self.flush()
        self.commits += 1


def backtest_run(*, completed: bool = False) -> dict[str, Any]:
    return {
        "id": "run-1",
        "owner_id": "user-1",
        "strategy_version_id": "version-1",
        "snapshot_id": "a" * 64,
        "created_at": "2026-10-12T02:00:00+00:00",
        "status": "completed" if completed else "queued",
        "progress": 100 if completed else 0,
        "config": {},
        "periods": (
            [{"trading_day": "2026-10-09", "equity": "1000", "cash": "900"}] if completed else []
        ),
        "trades": [{"symbol": "000001", "quantity": "100"}] if completed else [],
        "metrics": {"total_return": "0", "sharpe_ratio": None} if completed else {},
    }


def test_worker_result_save_keeps_separate_renamed_metadata():
    session = ForeignKeySession()
    store = SqlAlchemyBacktestStore(cast(Session, session))
    run = backtest_run()
    store.save(run, b"[]")
    row = session.rows["backtest_runs", (run["id"],)]
    row.name = "用户新名称"
    store.save({**run, "name": "worker旧名称"}, b"[]")
    result = store.get(run["id"])
    assert result is not None and result["name"] == "用户新名称"
    assert json.loads(row.payload_json)["name"] == "worker旧名称"


@pytest.mark.parametrize("completed", [False, True])
@pytest.mark.parametrize("streamed", [False, True])
def test_save_flushes_parents_before_snapshot_and_result_children(completed, streamed) -> None:
    session = ForeignKeySession()
    store = SqlAlchemyBacktestStore(cast(Session, session))
    run = backtest_run(completed=completed)
    records = [{"symbol": "000001"}] if completed else []
    payload = json.dumps(records, ensure_ascii=False, sort_keys=True).encode()
    if streamed:
        with SnapshotSpool() as spool:
            for record in records:
                spool.append(record)
            run["snapshot_id"] = spool.finish()
            store.save(run, spool)
    else:
        store.save(run, payload)

    snapshot = session.get(DataSnapshotModel, run["snapshot_id"])
    assert snapshot.record_count == len(records)
    chunks = [row for (table, _), row in session.rows.items() if table == "data_snapshot_chunks"]
    assert gzip.decompress(b"".join(row.payload for row in chunks)) == payload
    assert store.get(run["id"]) == run
    assert session.commits == 1


def test_existing_snapshot_is_reused_and_completed_results_can_be_replaced() -> None:
    session = ForeignKeySession()
    store = SqlAlchemyBacktestStore(cast(Session, session))
    run = backtest_run()
    store.save(run, b"[]")
    chunk = session.rows[DataSnapshotChunkModel.__tablename__, (run["snapshot_id"], 0)]
    run = backtest_run(completed=True)
    store.save(run, b"[]")
    run["metrics"]["total_return"] = "0.1"
    store.save(run, b"[]")
    assert session.rows[DataSnapshotChunkModel.__tablename__, (run["snapshot_id"], 0)] is chunk
    assert store.get(run["id"]) == run
    assert session.get(BacktestRunModel, run["id"]).status == "completed"
    assert sum(table == "backtest_periods" for table, _ in session.rows) == 1
    assert sum(table == "simulated_trades" for table, _ in session.rows) == 1
    assert sum(table == "backtest_metrics" for table, _ in session.rows) == 2
    assert session.commits == 3


def test_status_writes_use_fresh_sessions_instead_of_long_running_read_connection():
    class BrokenReadSession:
        def get(self, *_args):
            raise AssertionError("不能复用失效读连接")

    row = BacktestRunModel(
        id="run-1", status="running", progress=5, payload_json=json.dumps(backtest_run())
    )
    sessions = []

    class StatusSession:
        committed = False
        closed = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.closed = True

        def get(self, _model, _key):
            return row

        def commit(self):
            self.committed = True

    def factory():
        session = StatusSession()
        sessions.append(session)
        return cast(Session, session)

    store = SqlAlchemyBacktestStore(cast(Session, BrokenReadSession()), factory)
    store.mark_running("run-1")
    store.update_status("run-1", {"execution": {"stage": "warmup"}, "progress": 10})
    store.mark_failed("run-1", "数据不足")
    result = json.loads(row.payload_json)
    assert result["status"] == "failed" and result["error"] == "数据不足"
    assert result["execution"]["stage"] == "warmup"
    assert len(sessions) == 3 and all(session.committed and session.closed for session in sessions)


@pytest.mark.parametrize("fail_enqueue", [False, True])
def test_backtest_and_job_are_created_in_one_transaction(fail_enqueue):
    class AtomicSession(ForeignKeySession):
        rollbacks = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        @contextmanager
        def begin(self):
            before = deepcopy(self.rows)
            try:
                yield
                self.commit()
            except Exception:
                self.rows = before
                self.pending.clear()
                self.rollbacks += 1
                raise

        def scalar(self, _statement):
            return None

        def add(self, row):
            if fail_enqueue and row.__tablename__ == "jobs":
                raise RuntimeError("fake lock wait timeout")
            super().add(row)

    session = AtomicSession()
    store = SqlAlchemyBacktestStore(cast(Session, object()), lambda: cast(Session, session))
    run = backtest_run()
    job = Job(
        "j", "backtest.run", "b", {"backtest_id": run["id"]}, datetime(2026, 10, 12, tzinfo=UTC)
    )
    if fail_enqueue:
        with pytest.raises(RuntimeError):
            store.create_with_job(run, job, object())
        assert session.rows == {} and session.commits == 0 and session.rollbacks == 1
    else:
        store.create_with_job(run, job, object())
        assert session.commits == 1
        assert ("backtest_runs", (run["id"],)) in session.rows
        assert ("jobs", ("j",)) in session.rows


@pytest.mark.parametrize("fail_lock", [False, True])
def test_backtest_submission_and_strategy_lock_share_commit_and_rollback(fail_lock):
    class AtomicSession(ForeignKeySession):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        @contextmanager
        def begin(self):
            before = deepcopy(self.rows)
            try:
                yield
                self.commit()
            except Exception:
                self.rows = before
                self.pending.clear()
                raise

        def scalar(self, _statement):
            return None

        def execute(self, statement):
            if statement.table.name == "strategy_versions":
                self.flush()
                if fail_lock:
                    raise RuntimeError("lock failed")
                self.rows["strategy_versions", ("version-1",)].state = "testing"
            else:
                super().execute(statement)

    session = AtomicSession()
    session.rows["strategy_versions", ("version-1",)] = StrategyVersionModel(
        id="version-1", state="draft"
    )
    store = SqlAlchemyBacktestStore(cast(Session, object()), lambda: cast(Session, session))
    run = backtest_run()
    job = Job("j", "backtest.run", "b", {}, datetime(2026, 10, 12, tzinfo=UTC))
    if fail_lock:
        with pytest.raises(RuntimeError, match="lock failed"):
            store.create_with_job(run, job, object(), object())
        assert list(session.rows) == [("strategy_versions", ("version-1",))]
        assert session.rows["strategy_versions", ("version-1",)].state == "draft"
        assert session.commits == 0
    else:
        store.create_with_job(run, job, object(), object())
        assert session.commits == 1
        assert session.rows["strategy_versions", ("version-1",)].state == "testing"
        assert ("backtest_runs", (run["id"],)) in session.rows
        assert ("jobs", ("j",)) in session.rows

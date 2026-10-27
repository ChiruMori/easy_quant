import json
from contextlib import contextmanager
from copy import deepcopy
from threading import RLock

from sqlalchemy import delete, select
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.orm import load_only

from easy_quant.application.ports.resource_lifecycle import ResourceGraph
from easy_quant.domain.scheduling.entities import Job, JobStatus
from easy_quant.domain.strategies.entities import StrategyState
from easy_quant.infrastructure.persistence.models.backtesting import (
    BacktestMetricModel,
    BacktestPeriodModel,
    BacktestRunModel,
    DataSnapshotChunkModel,
    DataSnapshotModel,
    SimulatedTradeModel,
)
from easy_quant.infrastructure.persistence.models.runtime_state import (
    ResourceLifecycleMutexModel,
    RuntimeDocumentModel,
)
from easy_quant.infrastructure.persistence.models.scheduling import JobModel
from easy_quant.infrastructure.persistence.models.strategies import (
    StrategyModel,
    StrategyVersionModel,
)
from easy_quant.infrastructure.persistence.repositories.strategies import (
    SqlAlchemyStrategyRepository,
)

NAMESPACES = (
    "subscriptions",
    "deliveries",
    "live_instances",
    "recommendations",
    "operations",
    "portfolio_ledger",
    "schedules",
    "audit_events",
)
LIST_NAMESPACES = {"subscriptions", "deliveries", "portfolio_ledger", "audit_events"}


class InMemoryResourceLifecycleStore:
    def __init__(self, container):
        self.container = container
        self.lock = RLock()

    def add_live_instance(self, instance, schedules=()):
        self.container.state.strategies.advance_state(
            instance["strategy_version_id"], StrategyState.LIVE
        )
        self.container.state.live_instances[instance["id"]] = instance
        for row in schedules:
            self.container.state.schedules[row["id"]] = row

    @contextmanager
    def guard(self):
        with self.lock:
            yield

    @contextmanager
    def transaction(self):
        with self.guard():
            yield from self._transaction()

    def _transaction(self):
        container = self.container
        state = container.state
        documents = {}
        for name in NAMESPACES:
            rows = getattr(state, name)
            documents[name] = (
                {str(index): row for index, row in enumerate(rows)}
                if name in LIST_NAMESPACES
                else dict(rows)
            )
        graph = deepcopy(
            ResourceGraph(
                dict(state.strategies.definitions),
                {
                    row.id: row
                    for key in state.strategies.definitions
                    for row in state.strategies.versions(key)
                },
                dict(container.backtests.rows),
                dict(container.jobs.items),
                documents,
            )
        )
        yield graph
        state.strategies.definitions = graph.strategies
        state.strategies.version_items = {
            key: [row for row in graph.versions.values() if row.strategy_id == key]
            for key in graph.strategies
        }
        container.backtests.rows.clear()
        container.backtests.rows.update(graph.backtests)
        container.jobs.items = graph.jobs
        for name, rows in graph.documents.items():
            setattr(state, name, list(rows.values()) if name in LIST_NAMESPACES else rows)


class SqlResourceLifecycleStore:
    def __init__(self, factory):
        self.factory = factory

    def add_live_instance(self, instance, schedules=()):
        with self.factory() as session, session.begin():
            session.add(
                RuntimeDocumentModel(
                    namespace="live_instances",
                    key=instance["id"],
                    payload_json=json.dumps(instance, ensure_ascii=False, default=str),
                )
            )
            for row in schedules:
                session.add(
                    RuntimeDocumentModel(
                        namespace="schedules",
                        key=row["id"],
                        payload_json=json.dumps(row, ensure_ascii=False, default=str),
                    )
                )
            SqlAlchemyStrategyRepository.advance_state_in_transaction(
                session,
                instance["strategy_version_id"],
                StrategyState.LIVE,
            )

    @contextmanager
    def guard(self):
        # 与创建、引用变更共享锁；独立连接使既有适配器的短提交不会提前释放锁。
        with self.factory() as session, session.begin():
            lock = insert(ResourceLifecycleMutexModel).values(key="singleton")
            session.execute(lock.on_duplicate_key_update(key=lock.inserted.key))
            yield

    @contextmanager
    def transaction(self):
        with self.guard():
            yield from self._transaction()

    def _transaction(self):
        with self.factory() as session, session.begin():
            # 锁定删除图，阻止 worker 领取任务或更新正在删除的记录。
            strategy_rows = list(session.scalars(select(StrategyModel).with_for_update()))
            version_rows = list(
                session.scalars(
                    select(StrategyVersionModel)
                    .options(
                        load_only(
                            StrategyVersionModel.id,
                            StrategyVersionModel.strategy_id,
                            StrategyVersionModel.number,
                            StrategyVersionModel.name,
                        )
                    )
                    .with_for_update()
                )
            )
            run_rows = list(
                session.scalars(
                    select(BacktestRunModel)
                    .options(
                        load_only(
                            BacktestRunModel.id,
                            BacktestRunModel.owner_id,
                            BacktestRunModel.strategy_version_id,
                            BacktestRunModel.snapshot_id,
                        )
                    )
                    .with_for_update()
                )
            )
            job_rows = list(
                session.scalars(
                    select(JobModel)
                    .options(
                        load_only(
                            JobModel.id,
                            JobModel.job_type,
                            JobModel.business_key,
                            JobModel.payload_json,
                            JobModel.available_at,
                            JobModel.status,
                        )
                    )
                    .with_for_update()
                )
            )
            document_rows = list(
                session.scalars(
                    select(RuntimeDocumentModel)
                    .where(RuntimeDocumentModel.namespace.in_(set(NAMESPACES) - {"audit_events"}))
                    .with_for_update()
                )
            )
            repository = SqlAlchemyStrategyRepository(session)
            graph = ResourceGraph(
                {row.id: repository._definition(row) for row in strategy_rows},
                {row.id: row for row in version_rows},
                {
                    row.id: {
                        "id": row.id,
                        "owner_id": row.owner_id,
                        "strategy_version_id": row.strategy_version_id,
                    }
                    for row in run_rows
                },
                {
                    row.id: Job(
                        row.id,
                        row.job_type,
                        row.business_key,
                        json.loads(row.payload_json),
                        row.available_at,
                        JobStatus(row.status),
                    )
                    for row in job_rows
                },
                {
                    name: {
                        row.key: json.loads(row.payload_json)
                        for row in document_rows
                        if row.namespace == name
                    }
                    for name in NAMESPACES
                },
            )
            yield graph
            for row in document_rows:
                if row.key not in graph.documents[row.namespace]:
                    session.delete(row)
            existing = {(row.namespace, row.key) for row in document_rows}
            for name, rows in graph.documents.items():
                for key, value in rows.items():
                    if (name, key) not in existing:
                        session.add(
                            RuntimeDocumentModel(
                                namespace=name,
                                key=key,
                                payload_json=json.dumps(value, ensure_ascii=False, default=str),
                            )
                        )
            for row in job_rows:
                if row.id not in graph.jobs:
                    session.delete(row)
            snapshots = set()
            for row in run_rows:
                if row.id not in graph.backtests:
                    snapshots.add(row.snapshot_id)
                    for model in (BacktestPeriodModel, SimulatedTradeModel, BacktestMetricModel):
                        session.execute(delete(model).where(model.run_id == row.id))
                    session.delete(row)
            session.flush()
            for snapshot_id in snapshots:
                if (
                    session.scalar(
                        select(BacktestRunModel.id)
                        .where(BacktestRunModel.snapshot_id == snapshot_id)
                        .limit(1)
                    )
                    is None
                ):
                    session.execute(
                        delete(DataSnapshotChunkModel).where(
                            DataSnapshotChunkModel.snapshot_id == snapshot_id
                        )
                    )
                    session.execute(
                        delete(DataSnapshotModel).where(DataSnapshotModel.id == snapshot_id)
                    )
            for row in version_rows:
                if row.id not in graph.versions:
                    session.delete(row)
            session.flush()
            for row in strategy_rows:
                if row.id not in graph.strategies:
                    session.delete(row)
                else:
                    row.current_version_id = graph.strategies[row.id].current_version_id

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from threading import RLock
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.orm import Session, sessionmaker

from easy_quant.application.ports.live_tracking import LiveTrackingState
from easy_quant.infrastructure.persistence.models.runtime_state import RuntimeDocumentModel
from easy_quant.infrastructure.persistence.repositories.runtime_documents import (
    SqlJsonDict,
    SqlJsonList,
)


class InMemoryLiveTrackingStore:
    """Explicit test adapter; publish copied state only after successful completion."""

    def __init__(self, state: Any) -> None:
        self.state = state
        self._lock = RLock()

    @contextmanager
    def transaction(self) -> Iterator[LiveTrackingState]:
        with self._lock:
            working = LiveTrackingState(
                deepcopy(self.state.live_instances),
                deepcopy(self.state.recommendations),
                deepcopy(self.state.operations),
                deepcopy(self.state.portfolio_ledger),
                deepcopy(self.state.audit_events),
            )
            yield working
            self.state.live_instances = working.instances
            self.state.recommendations = working.recommendations
            self.state.operations = working.operations
            self.state.portfolio_ledger = working.ledger
            self.state.audit_events = working.audit


class SqlLiveTrackingStore:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self.factory = factory

    @contextmanager
    def transaction(self) -> Iterator[LiveTrackingState]:
        with self.factory() as session, session.begin():
            # The no-op upsert obtains an InnoDB write lock even on the first request.
            lock = insert(RuntimeDocumentModel).values(
                namespace="live_action_mutex",
                key="singleton",
                payload_json="{}",
            )
            session.execute(lock.on_duplicate_key_update(key=lock.inserted.key))
            session.scalar(
                select(RuntimeDocumentModel)
                .where(
                    RuntimeDocumentModel.namespace == "live_action_mutex",
                    RuntimeDocumentModel.key == "singleton",
                )
                .with_for_update()
            )
            yield LiveTrackingState(
                SqlJsonDict(session, "live_instances", commit_on_write=False),
                cast(Any, SqlJsonDict(session, "recommendations", commit_on_write=False)),
                SqlJsonDict(session, "operations", commit_on_write=False),
                SqlJsonList(session, "portfolio_ledger", commit_on_write=False),
                SqlJsonList(session, "audit_events", commit_on_write=False),
            )

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from easy_quant.domain.live_tracking.entities import Recommendation
from easy_quant.domain.live_tracking.ledger import ActualOperation, PortfolioLedgerEntry


class InMemoryLiveTrackingRepository:
    def __init__(self) -> None:
        self.recommendations: dict[str, Recommendation] = {}
        self.operations: dict[str, ActualOperation] = {}
        self.ledger: list[PortfolioLedgerEntry] = []

    @contextmanager
    def transaction(self) -> Iterator[None]:
        snapshot = (dict(self.recommendations), dict(self.operations), list(self.ledger))
        try:
            yield
        except Exception:
            self.recommendations, self.operations, self.ledger = snapshot
            raise

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from easy_quant.application.ports.core import IdGenerator
from easy_quant.domain.live_tracking.entities import Recommendation, RecommendationStatus
from easy_quant.domain.live_tracking.ledger import (
    ActualOperation,
    OperationKind,
    PortfolioLedgerEntry,
    entry_for_operation,
)
from easy_quant.domain.shared.errors import StateConflictError


class RecommendationActionService:
    def __init__(self, ids: IdGenerator) -> None:
        self.ids = ids
        self.operations: dict[str, ActualOperation] = {}
        self.ledger: list[PortfolioLedgerEntry] = []

    def apply(
        self,
        recommendation: Recommendation,
        kind: OperationKind,
        idempotency_key: str,
        expected_version: int,
        now: datetime,
        *,
        symbol: str | None = None,
        action: str | None = None,
        quantity: Decimal = Decimal(0),
        price: Decimal = Decimal(0),
        fee: Decimal = Decimal(0),
    ) -> ActualOperation:
        existing = self.operations.get(idempotency_key)
        if existing:
            return existing
        if (
            recommendation.version != expected_version
            or recommendation.status is not RecommendationStatus.PENDING
        ):
            raise StateConflictError("建议已被其他请求处理")
        if kind is OperationKind.CONFIRM:
            symbol = recommendation.instrument_id
            action = recommendation.action
            quantity = Decimal(recommendation.quantity)
        operation = ActualOperation(
            self.ids.new(),
            recommendation.id,
            recommendation.owner_id,
            kind,
            idempotency_key,
            now,
            symbol,
            action,
            quantity,
            price,
            fee,
        )
        entry = entry_for_operation(self.ids.new(), recommendation.live_instance_id, operation)
        recommendation.status = {
            OperationKind.CONFIRM: RecommendationStatus.CONFIRMED,
            OperationKind.REJECT: RecommendationStatus.REJECTED,
            OperationKind.CORRECT: RecommendationStatus.CORRECTED,
        }[kind]
        recommendation.version += 1
        self.operations[idempotency_key] = operation
        if entry:
            self.ledger.append(entry)
        return operation

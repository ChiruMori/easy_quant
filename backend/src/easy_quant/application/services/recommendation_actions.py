from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Any

from easy_quant.application.ports.core import Clock, IdGenerator
from easy_quant.application.ports.live_tracking import LiveTrackingState, LiveTrackingStore
from easy_quant.domain.live_tracking.entities import RecommendationStatus
from easy_quant.domain.live_tracking.ledger import (
    ActualOperation,
    OperationKind,
    PortfolioLedgerEntry,
    entry_for_operation,
    rebuild_portfolio,
)
from easy_quant.domain.shared.errors import NotFoundError, StateConflictError


@dataclass(frozen=True, slots=True)
class ActionCommand:
    kind: OperationKind
    idempotency_key: str
    expected_version: int
    symbol: str | None = None
    action: str | None = None
    quantity: Decimal = Decimal(0)
    price: Decimal = Decimal(0)
    fee: Decimal = Decimal(0)

    def fingerprint(self, recommendation_id: str) -> str:
        for value in (self.quantity, self.price, self.fee):
            if not value.is_finite() or value < 0:
                raise StateConflictError("成交数量、价格和费用必须为有限非负数")
        # Decimal equality, including trailing zeroes, must yield the same request identity.
        values = (
            recommendation_id,
            self.kind.value,
            self.expected_version,
            self.symbol,
            self.action,
            canonical_decimal(self.quantity),
            canonical_decimal(self.price),
            canonical_decimal(self.fee),
        )
        return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()


def canonical_decimal(value: Decimal) -> str:
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def ledger_entries(state: LiveTrackingState, instance_id: str) -> list[PortfolioLedgerEntry]:
    return [
        PortfolioLedgerEntry(
            str(item["id"]),
            str(item["live_instance_id"]),
            str(item["operation_id"]),
            datetime.fromisoformat(str(item["occurred_at"])),
            Decimal(str(item["cash_delta"])),
            str(item["symbol"]) if item.get("symbol") else None,
            Decimal(str(item["quantity_delta"])),
            Decimal(str(item["price"])),
            int(item.get("sequence", 0)),
        )
        for item in state.ledger
        if item["live_instance_id"] == instance_id
    ]


def actual_portfolio(state: LiveTrackingState, instance_id: str):
    instance = state.instances[instance_id]
    return rebuild_portfolio(
        Decimal(str(instance.get("initial_cash", "100000"))), ledger_entries(state, instance_id)
    )


def audit_row(
    ids: IdGenerator,
    now: datetime,
    owner_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str,
    before: dict[str, object],
    after: dict[str, object],
    *,
    trigger_source: str = "api",
) -> dict[str, object]:
    return {
        "id": ids.new(),
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "occurred_at": now.isoformat(),
        "trigger_source": trigger_source,
        "actor_user_id": owner_id,
        "before_summary": before,
        "after_summary": after,
    }


class RecommendationActionService:
    def __init__(self, store: LiveTrackingStore, clock: Clock, ids: IdGenerator) -> None:
        self.store, self.clock, self.ids = store, clock, ids

    def apply(
        self, recommendation_id: str, owner_id: str, command: ActionCommand
    ) -> dict[str, Any]:
        fingerprint = command.fingerprint(recommendation_id)
        storage_key = hashlib.sha256(
            json.dumps([owner_id, command.idempotency_key]).encode()
        ).hexdigest()
        with self.store.transaction() as state:
            found = next(
                (
                    (instance_id, index, row)
                    for instance_id, items in state.recommendations.items()
                    for index, row in enumerate(items)
                    if row["id"] == recommendation_id
                ),
                None,
            )
            if found is None:
                raise NotFoundError("recommendation")
            instance_id, index, stored = found
            instance = state.instances.get(instance_id)
            if (
                instance is None
                or instance["owner_id"] != owner_id
                or stored["owner_id"] != owner_id
            ):
                raise NotFoundError("recommendation")
            existing = state.operations.get(storage_key)
            if existing is not None:
                if (
                    existing.get("owner_id") != owner_id
                    or existing.get("request_fingerprint") != fingerprint
                ):
                    raise StateConflictError("幂等键已用于不同操作")
                return dict(existing["response"])
            legacy = state.operations.get(command.idempotency_key)
            if legacy is not None:
                if legacy.get("recommendation_id") != recommendation_id:
                    # Old global keys cannot safely identify another user's request.
                    legacy_owner = legacy.get("owner_id")
                    if legacy_owner == owner_id or legacy_owner is None:
                        raise StateConflictError("旧幂等键已被使用，请使用新键")
                else:
                    if legacy.get("kind") != command.kind.value:
                        raise StateConflictError("幂等键已用于不同操作")
                    # Legacy rows did not save full request fields: do not assume an exact replay.
                    raise StateConflictError("旧操作缺少请求身份，请查看建议和账本确认处理结果")
            if (
                int(stored["version"]) != command.expected_version
                or stored["status"] != RecommendationStatus.PENDING.value
            ):
                raise StateConflictError("建议已被其他请求处理")
            now = self.clock.now()
            symbol = (
                stored["instrument_id"] if command.kind is OperationKind.CONFIRM else command.symbol
            )
            action = stored["action"] if command.kind is OperationKind.CONFIRM else command.action
            quantity = (
                Decimal(str(stored["quantity"]))
                if command.kind is OperationKind.CONFIRM
                else command.quantity
            )
            price = command.price
            if command.kind is OperationKind.CONFIRM and price == 0:
                price = Decimal(str(stored.get("suggested_price") or "0"))
            operation = ActualOperation(
                self.ids.new(),
                recommendation_id,
                owner_id,
                command.kind,
                command.idempotency_key,
                now,
                symbol,
                action,
                quantity,
                price,
                command.fee,
            )
            entry = entry_for_operation(self.ids.new(), instance_id, operation)
            entries = ledger_entries(state, instance_id)
            if entry is not None:
                entry = replace(
                    entry, sequence=max((row.sequence for row in entries), default=0) + 1
                )
                entries.append(entry)
            portfolio = rebuild_portfolio(
                Decimal(str(instance.get("initial_cash", "100000"))), entries
            )
            status = {
                OperationKind.CONFIRM: RecommendationStatus.CONFIRMED,
                OperationKind.REJECT: RecommendationStatus.REJECTED,
                OperationKind.CORRECT: RecommendationStatus.CORRECTED,
            }[command.kind]
            response = {
                "id": operation.id,
                "kind": command.kind.value,
                "recommendation_status": status.value,
                "version": int(stored["version"]) + 1,
            }
            # No write occurs before the complete candidate ledger has passed validation.
            state.operations[storage_key] = {
                "id": operation.id,
                "kind": command.kind.value,
                "recommendation_id": recommendation_id,
                "owner_id": owner_id,
                "idempotency_key": command.idempotency_key,
                "occurred_at": now.isoformat(),
                "symbol": symbol,
                "action": action,
                "quantity": str(quantity),
                "price": str(price),
                "fee": str(command.fee),
                "request_fingerprint": fingerprint,
                "response": response,
            }
            if entry is not None:
                state.ledger.append(
                    {
                        "id": entry.id,
                        "live_instance_id": instance_id,
                        "operation_id": operation.id,
                        "occurred_at": entry.occurred_at.isoformat(),
                        "cash_delta": str(entry.cash_delta),
                        "symbol": entry.symbol,
                        "quantity_delta": str(entry.quantity_delta),
                        "price": str(entry.price),
                        "sequence": entry.sequence,
                    }
                )
            items = list(state.recommendations[instance_id])
            items[index] = {**stored, "status": status.value, "version": response["version"]}
            state.recommendations[instance_id] = items
            state.instances[instance_id] = {
                **instance,
                "cash": str(portfolio.cash),
                "positions": {key: str(value) for key, value in portfolio.positions.items()},
                "costs": {key: str(value) for key, value in portfolio.costs.items()},
            }
            state.audit.append(
                audit_row(
                    self.ids,
                    now,
                    owner_id,
                    command.kind.value,
                    "recommendation",
                    recommendation_id,
                    {"status": stored["status"], "version": int(stored["version"])},
                    {
                        "status": status.value,
                        "version": response["version"],
                        "operation_id": operation.id,
                    },
                )
            )
            return response

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from decimal import Decimal

from easy_quant.application.ports.core import Clock, IdGenerator
from easy_quant.application.ports.live_tracking import LiveTrackingStore
from easy_quant.application.services.recommendation_actions import (
    actual_portfolio,
    audit_row,
    canonical_decimal,
    ledger_entries,
)
from easy_quant.domain.live_tracking.ledger import (
    ActualOperation,
    OperationKind,
    PortfolioLedgerEntry,
    entry_for_operation,
    rebuild_portfolio,
)
from easy_quant.domain.live_tracking.reservations import (
    ensure_available,
    reservations,
    validate_lot,
)
from easy_quant.domain.shared.errors import NotFoundError, StateConflictError


@dataclass(frozen=True)
class ManualCommand:
    idempotency_key: str
    symbol: str
    action: str
    quantity: Decimal
    price: Decimal
    fee: Decimal
    risk_acknowledged: bool = False
    confirmed_increase: Decimal = Decimal(0)


class ManualOperationService:
    def __init__(self, store: LiveTrackingStore, clock: Clock, ids: IdGenerator):
        self.store, self.clock, self.ids = store, clock, ids

    def apply(
        self, instance_id: str, owner_id: str, command: ManualCommand, *, preview: bool = False
    ):
        validate_lot(command.quantity)
        if not command.confirmed_increase.is_finite() or command.confirmed_increase < 0:
            raise StateConflictError("追加资金必须为有限非负数")
        identity = json.dumps(
            [
                instance_id,
                command.symbol,
                command.action,
                canonical_decimal(command.quantity),
                canonical_decimal(command.price),
                canonical_decimal(command.fee),
                canonical_decimal(command.confirmed_increase),
            ],
            ensure_ascii=True,
        )
        fingerprint = hashlib.sha256(identity.encode()).hexdigest()
        key = hashlib.sha256(json.dumps([owner_id, command.idempotency_key]).encode()).hexdigest()
        with self.store.transaction() as state:
            instance = state.instances.get(instance_id)
            if instance is None or instance["owner_id"] != owner_id:
                raise NotFoundError("live_instance")
            existing = state.operations.get(key)
            if existing and not preview:
                if existing.get("request_fingerprint") != fingerprint:
                    raise StateConflictError("幂等键已用于不同操作")
                return existing["response"]
            if instance["status"] == "terminated":
                raise StateConflictError("已终止实盘不能添加操作")
            now = self.clock.now()
            operation = ActualOperation(
                self.ids.new(),
                "",
                owner_id,
                OperationKind.CORRECT,
                command.idempotency_key,
                now,
                command.symbol,
                command.action,
                command.quantity,
                command.price,
                command.fee,
            )
            entry = entry_for_operation(self.ids.new(), instance_id, operation)
            assert entry is not None
            entries = ledger_entries(state, instance_id)
            sequence = max((row.sequence for row in entries), default=0)
            locked = reservations(state.recommendations.get(instance_id, []))
            portfolio = actual_portfolio(state, instance_id)
            previous_cash = portfolio.cash
            increase = max(Decimal(0), locked.cash - portfolio.cash - entry.cash_delta)
            if (
                command.action == "sell"
                and portfolio.positions.get(command.symbol, Decimal(0))
                - locked.positions.get(command.symbol, Decimal(0))
                < command.quantity
            ):
                raise StateConflictError("可用持仓不足，不能占用锁定持仓")
            response = {
                "id": operation.id,
                "required_increase": str(increase),
                "capital_pool": str(
                    Decimal(str(instance.get("initial_cash", "100000")))
                    + Decimal(str(instance.get("capital_added", 0)))
                    + increase
                ),
            }
            if preview:
                return response
            if not command.risk_acknowledged:
                raise StateConflictError("请确认手动操作可能偏离策略、影响收益及重复记账的风险")
            if increase != command.confirmed_increase:
                raise StateConflictError(f"资金池需追加 {increase}，请重新核对并确认")
            additions: list[PortfolioLedgerEntry] = []
            if increase:
                additions.append(
                    PortfolioLedgerEntry(
                        self.ids.new(),
                        instance_id,
                        operation.id,
                        now,
                        increase,
                        sequence=sequence + 1,
                    )
                )
            additions.append(replace(entry, sequence=sequence + len(additions) + 1))
            portfolio = rebuild_portfolio(
                Decimal(str(instance.get("initial_cash", "100000"))),
                entries + additions,
                {
                    key: Decimal(str(value))
                    for key, value in instance.get("initial_positions", {}).items()
                },
            )
            ensure_available(portfolio, locked)
            for row in additions:
                state.ledger.append(
                    {
                        "id": row.id,
                        "live_instance_id": instance_id,
                        "operation_id": operation.id,
                        "occurred_at": row.occurred_at.isoformat(),
                        "cash_delta": str(row.cash_delta),
                        "symbol": row.symbol,
                        "quantity_delta": str(row.quantity_delta),
                        "price": str(row.price),
                        "sequence": row.sequence,
                    }
                )
            state.operations[key] = {
                "id": operation.id,
                "live_instance_id": instance_id,
                "owner_id": owner_id,
                "kind": "manual",
                "symbol": command.symbol,
                "action": command.action,
                "quantity": canonical_decimal(command.quantity),
                "price": canonical_decimal(command.price),
                "fee": canonical_decimal(command.fee),
                "occurred_at": now.isoformat(),
                "capital_increase": str(increase),
                "request_fingerprint": fingerprint,
                "response": response,
            }
            state.instances[instance_id] = {
                **instance,
                "capital_added": str(Decimal(str(instance.get("capital_added", 0))) + increase),
                "cash": str(portfolio.cash),
                "positions": {key: str(value) for key, value in portfolio.positions.items()},
                "costs": {key: str(value) for key, value in portfolio.costs.items()},
            }
            state.audit.append(
                audit_row(
                    self.ids,
                    now,
                    owner_id,
                    "manual_trade",
                    "live_instance",
                    instance_id,
                    {"cash": str(previous_cash)},
                    {
                        "operation_id": operation.id,
                        "capital_increase": str(increase),
                        "risk_acknowledged": True,
                    },
                )
            )
            return response

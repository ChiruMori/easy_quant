from datetime import timedelta
from decimal import Decimal

import pytest

from easy_quant.domain.live_tracking.ledger import (
    ActualOperation,
    OperationKind,
    PortfolioLedgerEntry,
    entry_for_operation,
    rebuild_portfolio,
)
from easy_quant.domain.shared.errors import StateConflictError


def test_confirm_reject_correct_and_cost_rebuild(fixed_now) -> None:
    confirm = ActualOperation(
        "o1",
        "r1",
        "u",
        OperationKind.CONFIRM,
        "key1",
        fixed_now,
        "000001",
        "buy",
        Decimal(10),
        Decimal(10),
        Decimal(1),
    )
    entry = entry_for_operation("e1", "live", confirm)
    assert entry is not None
    rejected = ActualOperation("o2", "r2", "u", OperationKind.REJECT, "key2", fixed_now, None)
    assert entry_for_operation("e2", "live", rejected) is None
    corrected = ActualOperation(
        "o3",
        "r3",
        "u",
        OperationKind.CORRECT,
        "key3",
        fixed_now + timedelta(seconds=1),
        "000001",
        "sell",
        Decimal(2),
        Decimal(12),
        Decimal(1),
    )
    second = entry_for_operation("e3", "live", corrected)
    assert second is not None
    state = rebuild_portfolio(Decimal(1000), [entry, second])
    assert (
        state.cash == Decimal(922)
        and state.positions["000001"] == 8
        and state.costs["000001"] == 10
    )


def test_negative_cash_and_position_are_rejected(fixed_now) -> None:
    with pytest.raises(StateConflictError):
        rebuild_portfolio(Decimal(1), [PortfolioLedgerEntry("e", "l", "o", fixed_now, Decimal(-2))])
    with pytest.raises(StateConflictError):
        rebuild_portfolio(
            Decimal(10),
            [
                PortfolioLedgerEntry(
                    "e", "l", "o", fixed_now, Decimal(1), "000001", Decimal(-1), Decimal(1)
                )
            ],
        )

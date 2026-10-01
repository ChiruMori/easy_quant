from decimal import Decimal

from easy_quant.domain.live_tracking.ledger import rebuild_portfolio


def test_empty_portfolio_comes_only_from_ledger() -> None:
    state = rebuild_portfolio(Decimal("100000"), [])
    assert state.cash == Decimal("100000") and state.positions == {}

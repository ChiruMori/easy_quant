from datetime import UTC, date, datetime
from decimal import Decimal as D

import pytest

from easy_quant.domain.backtesting.engine import PhasedBacktestSession
from easy_quant.domain.backtesting.entities import BacktestConfig
from easy_quant.domain.backtesting.execution import MarketBar
from easy_quant.domain.market_data.corporate_actions import CorporateAction, CorporateActionBook
from easy_quant.domain.shared.errors import StateConflictError
from easy_quant.domain.strategies.entities import Signal
from tests.fakes.corporate_action_fixture import AS_OF, bar, coverage, event


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({}, 9),
        (
            {
                "kinds": ["bonus"],
                "cash_per_share": "0",
                "share_multiplier": "1.5",
                "shares_listing_date": "2026-09-23",
            },
            10 / 1.5,
        ),
        (
            {
                "kinds": ["capitalization"],
                "cash_per_share": "0",
                "share_multiplier": "2",
                "shares_listing_date": "2026-09-23",
            },
            5,
        ),
        (
            {
                "kinds": ["split"],
                "cash_per_share": "0",
                "share_multiplier": "10",
                "shares_listing_date": "2026-09-22",
            },
            1,
        ),
        (
            {
                "kinds": ["consolidation"],
                "cash_per_share": "0",
                "share_multiplier": "0.5",
                "shares_listing_date": "2026-09-22",
            },
            20,
        ),
        (
            {
                "kinds": ["cash_dividend", "bonus", "rights"],
                "share_multiplier": "1.5",
                "rights_ratio": "0.5",
                "rights_price": "4",
                "shares_listing_date": "2026-09-22",
            },
            5.5,
        ),
    ],
)
def test_all_events_reference_price_and_raw_volume(changes, expected):
    row = event(**changes)
    action = CorporateAction.parse(row)
    assert float(action.ex_reference) == pytest.approx(expected)
    book = CorporateActionBook([row, coverage(row)])
    raw = [bar(), bar("2026-09-22", str(expected))]
    adjusted = book.adjust(raw, "000001", AS_OF)
    assert adjusted[0]["close"] == pytest.approx(adjusted[1]["close"])
    assert adjusted[0]["volume"] == "1000" and adjusted[0]["amount"] == "10000"
    assert raw[0]["close"] == "10" and adjusted[0]["raw_close"] == "10"
    hfq = book.adjust(raw, "000001", AS_OF, mode="hfq")
    assert hfq[1]["close"] / hfq[0]["close"] == pytest.approx(
        adjusted[1]["close"] / adjusted[0]["close"]
    )


def test_future_anchor_events_and_revisions_do_not_rewrite_past():
    first = event()
    future = event(
        event_id="000001:2026-10-02",
        record_date="2026-10-01",
        ex_date="2026-10-02",
        cash_pay_date="2026-10-02",
        available_at="2026-09-24T12:00:00+08:00",
    )
    book = CorporateActionBook([first, future, coverage(first, future)])
    before = datetime(2026, 9, 21, 12, tzinfo=UTC)
    assert book.adjust([bar()], "000001", before)[0]["close"] == 10
    assert book.adjust([bar()], "000001", AS_OF)[0]["close"] == 9
    revised = event(cash_per_share="2", available_at="2026-10-01T12:00:00+08:00")
    assert (
        CorporateActionBook([first, revised, coverage(first, revised)]).adjust(
            [bar()], "000001", AS_OF
        )[0]["close"]
        == 9
    )
    with pytest.raises(ValueError, match="锚点"):
        book.adjust([bar()], "000001", before, anchor=date(2026, 10, 2))


def test_missing_coverage_late_information_legacy_and_candidate_fail_closed():
    with pytest.raises(StateConflictError, match="覆盖"):
        CorporateActionBook([]).adjust([bar()], "000001", AS_OF)
    late = event(available_at="2026-09-30T00:00:00+00:00")
    with pytest.raises(StateConflictError, match="当时可获知"):
        CorporateActionBook([late, coverage(late)]).adjust([bar()], "000001", AS_OF)
    with pytest.raises(StateConflictError, match="原价"):
        CorporateActionBook([coverage()]).adjust([{**bar(), "adjustment": "qfq"}], "000001", AS_OF)
    candidate = {
        "record_kind": "candidate",
        "symbol": "000001",
        "ex_date": "2026-09-22",
        "record_key": "new",
    }
    with pytest.raises(StateConflictError, match="候选"):
        CorporateActionBook([coverage(), candidate]).adjust([bar()], "000001", AS_OF)


def session():
    return PhasedBacktestSession(
        BacktestConfig("v", (), date(2026, 9, 21), date(2026, 9, 25), D(1000), D(0), D(0))
    )


def advance(s, day, price, signals=(), events=()):
    s.advance(
        date(2026, 9, day),
        [MarketBar(date(2026, 9, day), "000001", D(price), open=D(price))] if price else [],
        lambda phase: list(signals) if phase == "after_market" else [],
        events,
    )


def test_cash_entitlement_equity_and_delayed_payment_even_when_sold_or_suspended():
    action = CorporateAction.parse(event())
    s = session()
    advance(s, 21, "10", [Signal("000001", "buy", D(100), "test")], (action,))
    advance(s, 22, None, events=(action,))
    assert s.periods[-1].equity == 1000
    assert s.portfolio.cash == 0 and s.portfolio.receivable_cash == 100
    advance(s, 23, "9", [Signal("000001", "sell", D(100), "test")], (action,))
    assert s.portfolio.cash == 900 and s.periods[-1].equity == 1000
    advance(s, 24, "9", events=(action,))
    assert s.portfolio.cash == 1000 and s.portfolio.receivable_cash == 0
    s.corporate_ledger.open(date(2026, 9, 24), s.portfolio, (action,), s.marks)
    assert s.portfolio.cash == 1000


def test_cancelled_registered_event_stops_instead_of_paying_old_terms():
    s = session()
    action = CorporateAction.parse(event())
    advance(s, 21, "10", [Signal("000001", "buy", D(100), "test")], (action,))
    with pytest.raises(StateConflictError, match="取消"):
        advance(s, 22, "9", events=())


def test_new_ex_day_buyer_has_no_dividend_and_unlisted_shares_are_not_sellable():
    action = CorporateAction.parse(
        event(
            cash_per_share="0",
            share_multiplier="2",
            kinds=["bonus"],
            shares_listing_date="2026-09-24",
        )
    )
    s = session()
    advance(s, 21, "10", [Signal("000001", "buy", D(100), "test")], (action,))
    advance(s, 22, "5", [Signal("000001", "sell", D(200), "test")], (action,))
    assert s.portfolio.position("000001") == 200
    assert len(s.trades) == 1 and s.periods[-1].equity == 1000
    advance(s, 24, "5", [Signal("000001", "sell", D(200), "test")], (action,))
    assert s.portfolio.cash == 1000 and s.portfolio.position("000001") == 0
    fresh = session()
    advance(fresh, 21, "10", events=(action,))
    advance(fresh, 22, "5", [Signal("000001", "buy", D(100), "test")], (action,))
    advance(fresh, 24, "5", events=(action,))
    assert fresh.portfolio.position("000001") == 100


@pytest.mark.parametrize(
    "changes",
    [
        {"kinds": ["cash_dividend", "rights"], "rights_ratio": "0.5", "rights_price": "4"},
        {
            "kinds": ["consolidation"],
            "cash_per_share": "0",
            "share_multiplier": "0.333",
            "shares_listing_date": "2026-09-22",
        },
    ],
)
def test_unsupported_rights_and_fractional_shares_abort(changes):
    s = session()
    with pytest.raises(StateConflictError):
        advance(
            s,
            21,
            "10",
            [Signal("000001", "buy", D(100), "test")],
            (CorporateAction.parse(event(**changes)),),
        )

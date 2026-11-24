import base64
import io
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from easy_quant.application.services.backtest_runtime import execute_backtest
from easy_quant.application.services.corporate_actions import (
    dividend_candidates,
    import_manifest,
    runtime_snapshot,
)
from easy_quant.application.services.factor_quick_test import quick_test_factor
from easy_quant.application.services.live_corporate_actions import (
    confirm_action,
    ensure_reconciled,
    list_pending,
)
from easy_quant.application.services.recommendation_actions import actual_portfolio
from easy_quant.domain.market_data.corporate_actions import DATASET, POLICY
from easy_quant.domain.shared.errors import NotFoundError, StateConflictError, ValidationError
from easy_quant.domain.strategies.entities import StrategyDefinition, StrategyVersion
from easy_quant.infrastructure.imports.tdx_corporate_actions import (
    archive_candidates,
    decode_records,
)
from easy_quant.infrastructure.persistence.repositories.runtime import InMemoryMarketDataStore
from easy_quant.strategy_api.context import RuntimeContext
from tests.fakes.corporate_action_fixture import AS_OF, bar, coverage, event
from tests.fakes.platform import make_test_container


def test_import_dry_run_immutable_retry_and_no_guessed_coverage():
    store = InMemoryMarketDataStore({}, {}, set())
    row = event()
    proof = coverage(row)
    proof["end_day"] = "2026-09-25"
    document = {
        "schema_version": POLICY,
        "source": "fixture",
        "evidence": "fixture:public-notice",
        "events": [row],
        "coverage": [proof],
    }
    proof["event_keys"] = import_manifest(store, {**document, "coverage": []}, AS_OF)["event_keys"]
    preview = import_manifest(store, document, AS_OF)
    assert not store.list_records(DATASET)
    assert preview["records"] == 2
    import_manifest(store, document, AS_OF, apply=True)
    first = store.list_records(DATASET)
    import_manifest(store, document, datetime(2026, 9, 26, tzinfo=UTC), apply=True)
    assert store.list_records(DATASET) == first
    invalid = {**document, "events": [event(cash_pay_date=None)]}
    with pytest.raises(ValidationError):
        import_manifest(store, invalid, AS_OF, apply=True)
    assert store.list_records(DATASET) == first
    with pytest.raises(ValidationError, match="覆盖"):
        import_manifest(
            store, {**document, "coverage": [{**proof, "event_keys": []}]}, AS_OF, apply=True
        )


def test_legacy_dividend_migration_only_creates_candidates_and_keeps_availability():
    rows = dividend_candidates(
        [
            {
                "record_key": "old",
                "symbol": "000001",
                "ex_dividend_date": "2026-09-22",
                "record_date": "2026-09-21",
                "cash_per_ten_shares": "10",
                "available_at": AS_OF.isoformat(),
            }
        ]
    )
    assert rows[0]["record_kind"] == "candidate"
    assert rows[0]["cash_per_ten_shares"] == "10"
    assert rows[0]["available_at"] == AS_OF.isoformat()
    assert "cash_pay_date" in rows[0]["missing"]


def test_actual_gbbq_fixed_binary_fixture_and_archive_bounds():
    # 官方公开归档前5条记录，1990–1991年深发展；固定样本，测试绝不访问下载地址。
    content = base64.b64decode(
        "BQAAAGMSJLDzEcmpU8C7GAaGajncvFxVFMPh0gAAAIA/YxIksPMRyamx54bAl/PoHKCuEBuzZkHhRSOQl0VjEiSw8xHJqcqNhf7uXmOKRluEtE5Jhn9AAAAAAGMSJLDzEcmpH/ejVhYN5Cz/6ZYd2JTEZ0WoPAxGYxIksPMRyanPYUcBz5fVSAY6QoZeK3UwQQAAAAA="
    )
    decoded = list(decode_records(content))
    assert decoded[2][:3] == ("000001", "1991-05-02", 1)
    assert decoded[2][3] == [3, 0, 4, 0]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(zipfile.ZipInfo("gbbq", (2026, 9, 24, 0, 0, 0)), content)
    candidates = archive_candidates(buffer.getvalue(), AS_OF)
    assert len(candidates) == 5 and not any(row["record_kind"] == "event" for row in candidates)
    assert {row["archive_snapshot_day"] for row in candidates} == {"2026-09-24"}
    with pytest.raises(ValueError):
        list(decode_records(content[:-1]))


def test_research_uses_qfq_execution_remains_raw_and_future_audit_is_private():
    row = event()
    data = {
        "decision_at": AS_OF.isoformat(),
        "price_policy": POLICY,
        "corporate_actions": [row, coverage(row)],
        "bars": {"000001": [bar(), bar("2026-09-22", "9")]},
    }
    context = RuntimeContext(data)
    assert context.history("000001")["close"].tolist() == [9, 9]
    assert context.history("000001", adjustment="raw")["close"].tolist() == [10, 9]
    assert "corporate_actions" not in context.data
    assert context.data["bars"]["000001"][0]["close"] == "10"


def test_compound_event_volume_and_vwap_use_distinct_adjustments():
    row = event(
        kinds=["cash_dividend", "bonus"], share_multiplier="2", shares_listing_date="2026-09-24"
    )
    context = RuntimeContext(
        {
            "decision_at": AS_OF.isoformat(),
            "price_policy": POLICY,
            "corporate_actions": [row, coverage(row)],
            "bars": {"000001": [bar()]},
        }
    )
    result = context.history("000001").iloc[0]
    assert result["close"] == 4.5
    assert result["volume"] == 1000 and result["amount"] == 10000
    assert result["adjusted_volume"] == 2000 and result["adjusted_vwap"] == 4.5
    assert result["raw_close"] == 10


@pytest.mark.parametrize("published", ["2026-09-18T12:00:00+08:00", "2026-09-21T12:00:00+08:00"])
def test_real_backtest_accounts_for_dividends_and_symbol_performance(fixed_now, published):
    container = make_test_container()
    row = event(available_at=published)
    container.market_data.upsert_records(DATASET, [row, coverage(row)])
    container.market_data.upsert_bars([bar(), *[bar(f"2026-09-{d}", "9") for d in (22, 23, 24)]])
    source = """def before_market(c,p):
    if c.data['trading_day']=='2026-09-21':
        return [{'symbol':'000001','action':'buy','quantity':100,'reason':'fixture'}]
    return []
def on_market(c,p):
    return []
def after_market(c,p):
    print(c.history('000001')['close'].iloc[-1])
    return []
"""
    container.state.strategies.add_definition(StrategyDefinition("s", "u", "fixture"))
    container.state.strategies.add_version(
        StrategyVersion("v", "s", 1, source, "fixture", fixed_now)
    )
    container.state.backtests["b"] = {
        "id": "b",
        "owner_id": "u",
        "strategy_version_id": "v",
        "config": {
            "start_day": "2026-09-21",
            "end_day": "2026-09-24",
            "initial_cash": "1000",
            "fee_rate": "0",
            "slippage_rate": "0",
        },
    }
    execute_backtest(container, "b")
    run = container.backtests.get("b")
    assert all(Decimal(p["equity"]) == 1000 for p in run["periods"])
    assert run["trades"][0]["price"] == "10.00"
    assert run["periods"][-1]["cash"] == "100.00"
    assert Decimal(run["symbol_performance"][0]["profit"]) == 0
    assert run["corporate_action_snapshot"] and run["assumptions"]["corporate_actions_sha256"]


def test_decision_snapshot_excludes_future_economic_versions_and_orders_late_bars():
    from easy_quant.application.services.corporate_actions import decision_snapshot

    current = event()
    future = event(available_at="2026-09-30T00:00:00+00:00", cash_per_share="2")
    snapshot = {"corporate_actions": [current, future, coverage(current, future)]}
    projected = decision_snapshot(snapshot, AS_OF)
    assert all(
        row.get("available_at") != future["available_at"]
        for row in projected["corporate_actions"]
        if row.get("record_kind") == "event"
    )
    late = {**bar(), "available_at": "2026-09-23T00:00:00+00:00"}
    context = RuntimeContext(
        {
            **projected,
            "decision_at": AS_OF.isoformat(),
            "bars": {"000001": [bar("2026-09-22", "9"), late]},
        }
    )
    rows = context.library("market.daily-bars", symbol="000001")
    assert [row["trading_day"] for row in rows] == ["2026-09-21", "2026-09-22"]


def test_market_comparison_does_not_show_dividend_as_price_loss():
    from easy_quant.application.services.chart_comparisons import comparison_series

    container = make_test_container()
    row = event()
    container.market_data.upsert_records(DATASET, [row, coverage(row)])
    container.market_data.upsert_bars([bar(), bar("2026-09-22", "9")])
    container.market_data.upsert_instruments(
        [{"symbol": "000001", "name": "fixture", "exchange": "SZSE"}]
    )
    container.state.backtests["b"] = {
        "id": "b",
        "owner_id": "u",
        "status": "succeeded",
        "config": {"start_day": "2026-09-21", "end_day": "2026-09-22", "initial_cash": "1000"},
        "periods": [{"trading_day": "2026-09-21"}, {"trading_day": "2026-09-22"}],
    }
    series = comparison_series(container, "backtest", "b", "u", symbol="000001")
    assert [Decimal(point["return_rate"]) for point in series["points"]] == [0, 0]


def test_real_factor_subprocess_adjusts_event_and_missing_coverage_is_reported():
    container = make_test_container()
    container.market_data = InMemoryMarketDataStore({}, {}, set())
    row = event()
    container.market_data.upsert_bars([bar(), bar("2026-09-22", "9")])
    with pytest.raises(StateConflictError):
        quick_test_factor(
            container, "technical.ma", {"symbol": "000001", "window": 2}, date(2026, 9, 22)
        )
    container.market_data.upsert_records(DATASET, [row, coverage(row)])
    result = quick_test_factor(
        container, "technical.ma", {"symbol": "000001", "window": 2}, date(2026, 9, 22)
    )
    assert result["result"]["value"] == 9


def live_container():
    container = make_test_container()
    container.market_data.upsert_bars([bar(), bar("2026-09-22", "9")])
    row = event()
    container.market_data.upsert_records(DATASET, [row, coverage(row)])
    container.state.live_instances["l"] = {
        "id": "l",
        "owner_id": "u",
        "status": "active",
        "started_at": "2026-09-20T00:00:00+08:00",
        "initial_cash": "1000",
        "initial_positions": {"000001": "100"},
    }
    return container, row


def test_live_confirmation_is_owned_atomic_idempotent_and_preserves_capital():
    container, row = live_container()
    pending = list_pending(container, "l", "u")
    assert pending[0]["gross_cash"] == "100"
    with pytest.raises(StateConflictError, match="核对"):
        ensure_reconciled(
            container,
            "l",
            container.authentication.clock.now(),
            runtime_snapshot(container.market_data),
        )
    payload = {
        "event_id": row["event_id"],
        "record_key": row["record_key"],
        "cash": "80.00",
        "share_delta": "0",
        "evidence": "券商到账摘要",
    }
    with pytest.raises(NotFoundError):
        list_pending(container, "l", "other-user")
    with pytest.raises(NotFoundError):
        confirm_action(container, "l", "other-user", payload)
    assert container.state.portfolio_ledger == []
    confirm_action(container, "l", "u", payload)
    confirm_action(container, "l", "u", payload)
    assert len(container.state.portfolio_ledger) == 1
    with container.live_tracking.transaction() as state:
        assert actual_portfolio(state, "l").cash == Decimal("1080")
    assert list_pending(container, "l", "u") == []
    with pytest.raises(StateConflictError):
        confirm_action(container, "l", "u", {**payload, "cash": "90"})
    assert len(container.state.portfolio_ledger) == 1


def test_live_old_pending_advice_is_invalidated_before_any_new_signal():
    container, _ = live_container()
    container.state.recommendations["l"] = [
        {
            "id": "old",
            "instrument_id": "000001",
            "decision_at": "2026-09-21T09:00:00+08:00",
            "status": "pending",
            "version": 0,
        }
    ]
    with pytest.raises(StateConflictError, match="失效"):
        ensure_reconciled(
            container,
            "l",
            container.authentication.clock.now(),
            runtime_snapshot(container.market_data),
        )
    assert container.state.recommendations["l"][0]["status"] == "rejected"

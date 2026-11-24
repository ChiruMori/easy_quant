from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest

from easy_quant.application.services.corporate_actions import (
    decision_snapshot,
    identity,
    runtime_snapshot,
)
from easy_quant.application.services.tdx_equity_sync import enrich_tdx_equity
from easy_quant.application.services.tdx_price_sync import prepare_tdx_prices
from easy_quant.domain.market_data.corporate_actions import CorporateActionBook
from easy_quant.domain.market_data.research_actions import TDX_PRICE_DATASET
from easy_quant.domain.shared.errors import StateConflictError
from easy_quant.infrastructure.persistence.repositories.runtime import InMemoryMarketDataStore
from easy_quant.strategy_api.context import RuntimeContext
from tests.fakes.corporate_action_fixture import AS_OF, bar


def candidate(symbol="000001", ex_date="2026-09-22", category=1, values=None):
    row = {
        "symbol": symbol,
        "ex_date": ex_date,
        "category": category,
        "values": values or ["10", "0", "0", "0"],
    }
    return {**row, "record_key": identity(row)}


def store_with_prices():
    store = InMemoryMarketDataStore({}, {}, set())
    store.upsert_bars(
        [
            {**bar(day, value), "source": "tdx-official"}
            for day, value in [
                ("2026-09-21", "10"),
                ("2026-09-22", "9"),
                ("2026-09-23", "9"),
                ("2026-09-24", "9"),
            ]
        ]
    )
    return store


def prepare(store, candidates, now=AS_OF, **kwargs):
    with patch(
        "easy_quant.application.services.tdx_price_sync.archive_candidates", return_value=candidates
    ):
        return prepare_tdx_prices(store, b"fixed-offline-archive", now, **kwargs)


def test_price_capability_works_without_equity_dates_and_raw_storage_is_unchanged():
    store = store_with_prices()
    original = store.list_bars()
    report = prepare(store, [candidate()])
    assert report["price_events"] == 1
    assert store.list_records(TDX_PRICE_DATASET) == []
    prepare(store, [candidate()], apply=True)
    context = RuntimeContext(
        {
            **decision_snapshot(runtime_snapshot(store), AS_OF),
            "decision_at": AS_OF.isoformat(),
            "bars": {"000001": original},
        }
    )
    assert list(context.history("000001")["close"]) == [9, 9, 9, 9]
    assert list(context.history("000001", adjustment="raw")["close"]) == [10, 9, 9, 9]
    assert list(context.history("000001", adjustment="hfq")["close"]) == [10, 10, 10, 10]
    assert store.list_bars() == original
    book = CorporateActionBook(runtime_snapshot(store)["corporate_actions"])
    with pytest.raises(StateConflictError, match="权益资料"):
        book.require_equity("000001", date(2026, 9, 22), AS_OF)
    book.require_equity("000001", date(2026, 9, 23), AS_OF)


def test_future_event_is_not_in_child_snapshot_and_unknown_event_only_blocks_affected_window():
    store = store_with_prices()
    prepare(store, [candidate(), candidate(ex_date="2026-09-26", category=15)], apply=True)
    snapshot = runtime_snapshot(store)
    early = datetime(2026, 9, 21, 12, tzinfo=UTC)
    child = decision_snapshot(snapshot, early)
    publication = next(
        row for row in child["corporate_actions"] if row["record_kind"] == "tdx_price_publication"
    )
    assert publication["events"] == [] and publication["issues"] == []
    book = CorporateActionBook(snapshot["corporate_actions"])
    book.require_coverage("000001", date(2026, 9, 21), date(2026, 9, 25), AS_OF)
    prepare(store, [candidate(), candidate(ex_date="2026-09-24", category=15)], apply=True)
    book = CorporateActionBook(runtime_snapshot(store)["corporate_actions"])
    with pytest.raises(StateConflictError, match="不能可靠转换"):
        book.require_coverage("000001", date(2026, 9, 21), date(2026, 9, 25), AS_OF)
    book.require_coverage("000001", date(2026, 9, 25), date(2026, 9, 25), AS_OF)


def test_rerun_reuses_context_and_source_revision_rebuilds_without_duplicate_application():
    store = store_with_prices()
    prepare(store, [candidate()], apply=True)
    with patch.object(
        store,
        "price_event_contexts",
        side_effect=AssertionError("unchanged events must reuse context"),
    ):
        assert (
            prepare(store, [candidate()], now=AS_OF + timedelta(days=1), apply=True)["items"][0][
                "status"
            ]
            == "reused"
        )
    prepare(
        store, [candidate(values=["20", "0", "0", "0"])], now=AS_OF + timedelta(days=1), apply=True
    )
    assert len(store.list_records(TDX_PRICE_DATASET)) == 1
    book = CorporateActionBook(runtime_snapshot(store)["corporate_actions"])
    assert book.adjust(store.list_bars(), "000001", AS_OF)[0]["close"] == 8


@pytest.mark.parametrize(
    "values", [["-1", "0", "0", "0"], ["0", "0", "0", "1"], ["1000", "0", "0", "0"]]
)
def test_bad_units_or_components_are_explicit_issues(values):
    assert prepare(store_with_prices(), [candidate(values=values)])["issue_count"] == 1


def test_actual_dividend_can_differ_from_price_adjustment_and_is_bound_to_source_terms():
    store = store_with_prices()
    prepare(store, [candidate()], apply=True)

    class Source:
        calls = 0

        def fetch(self, symbol):
            self.calls += 1
            return [
                {
                    "除权日": "2026-09-22",
                    "股权登记日": "2026-09-21",
                    "派息日": "2026-09-24",
                    "实施方案公告日期": "2026-09-18",
                    "派息比例": 12,
                    "送股比例": None,
                    "转增比例": None,
                }
            ]

    source = Source()
    assert enrich_tdx_equity(store, source, "000001", AS_OF)["added"] == 1
    assert enrich_tdx_equity(store, source, "000001", AS_OF)["added"] == 0
    assert source.calls == 1
    book = CorporateActionBook(runtime_snapshot(store)["corporate_actions"])
    book.require_equity("000001", date(2026, 9, 22), AS_OF)
    action = book.events("000001", AS_OF)[0]
    assert action.cash_per_share == Decimal("1.2")
    assert action.price_ratio == Decimal("0.9")
    assert action.cash_pay_date == date(2026, 9, 24)
    assert action.record_date == date(2026, 9, 21)


def test_future_ex_day_context_is_rebuilt_until_effective_date():
    store = store_with_prices()
    now = datetime(2026, 9, 23, 12, tzinfo=UTC)
    event = candidate(ex_date="2026-09-25")
    prepare(store, [event], now=now, apply=True)
    previous_key = store.list_records(TDX_PRICE_DATASET)[0]["events"][0]["record_key"]
    store.upsert_bars([{**bar("2026-09-24", "20"), "source": "tdx-official"}])
    prepare(store, [event], now=AS_OF, apply=True)
    result = store.list_records(TDX_PRICE_DATASET)[0]["events"][0]
    assert result["previous_close"] == "20" and result["record_key"] == previous_key


def test_multiple_symbols_and_unknown_share_types_do_not_poison_other_symbols():
    store = store_with_prices()
    store.upsert_bars([{**bar(), "symbol": "600519", "source": "tdx-official"}])
    result = prepare(store, [candidate(), candidate(symbol="600519", category=4)], apply=True)
    assert result["symbols"] == 2
    book = CorporateActionBook(runtime_snapshot(store)["corporate_actions"])
    assert book.adjust(store.list_bars(symbol="000001"), "000001", AS_OF)[0]["close"] == 9


def test_gaps_from_a_declared_raw_source_do_not_reject_tdx_history():
    store = store_with_prices()
    # 接入通达信前已有的原价补充，生产端仍禁止其他来源覆盖通达信。
    store.daily_bars[("000001", "2026-09-21")] = {**bar("2026-09-21", "10"), "source": "tencent"}
    prepare(store, [candidate()], apply=True)
    publication = store.list_records(TDX_PRICE_DATASET)[0]
    assert publication["context_sources"] == ["tdx-official", "tencent"]
    assert publication["supplemental_context_rows"] == 1


def test_share_listing_date_is_not_guessed_and_warrant_equity_is_separate():
    store = store_with_prices()
    prepare(store, [candidate(category=14)], apply=True)
    book = CorporateActionBook(runtime_snapshot(store)["corporate_actions"])
    assert book.adjust(store.list_bars(), "000001", AS_OF)[0]["close"] == 10
    with pytest.raises(StateConflictError, match="权证"):
        book.require_equity("000001", date(2026, 9, 22), AS_OF)
    child = decision_snapshot(runtime_snapshot(store), AS_OF)
    assert "equity_issues" not in child["corporate_actions"][0]


def test_unsupported_symbol_is_excluded_only_after_event_and_can_be_requested_explicitly():
    store = store_with_prices()
    prepare(store, [candidate(category=15)], apply=True)
    for at, expected in [(datetime(2026, 9, 21, 12, tzinfo=UTC), ["000001"]), (AS_OF, [])]:
        context = RuntimeContext(
            {
                **decision_snapshot(runtime_snapshot(store), at),
                "decision_at": at.isoformat(),
                "universe": ["000001"],
                "bars": {"000001": store.list_bars()},
            }
        )
        assert context.universe() == expected
        if not expected:
            with pytest.raises(StateConflictError):
                context.history("000001")
            with pytest.raises(ValueError):
                context.signal("000001", "buy", 0.1, "test", price=9)


def test_equity_source_timeout_is_killed_without_inheriting_application_secrets(monkeypatch):
    import subprocess

    from easy_quant.infrastructure.data_sources.cninfo_actions import CninfoEquitySource

    monkeypatch.setenv("DATABASE_URL", "never-export-this")

    def timeout(*args, **kwargs):
        assert "DATABASE_URL" not in kwargs["env"]
        assert kwargs["timeout"] == 25
        raise subprocess.TimeoutExpired(args[0], 25)

    with (
        patch(
            "easy_quant.infrastructure.data_sources.cninfo_actions.subprocess.run",
            side_effect=timeout,
        ),
        pytest.raises(RuntimeError, match="超时"),
    ):
        CninfoEquitySource().fetch("000001")


def test_equity_background_job_resumes_and_does_not_duplicate_completed_source_requests():
    from types import SimpleNamespace

    from easy_quant.application.ports.jobs import JobContinuation
    from easy_quant.infrastructure.persistence.repositories.jobs import InMemoryJobRepository
    from easy_quant.worker.handlers.corporate_actions import (
        enqueue_equity_enrichment,
        register_corporate_action_handlers,
    )
    from easy_quant.worker.registry import JobHandlerRegistry

    store = store_with_prices()
    prepare(store, [candidate()], apply=True)

    class Source:
        calls = 0

        def fetch(self, symbol):
            self.calls += 1
            return []

    source = Source()
    container = SimpleNamespace(
        market_data=store,
        jobs=InMemoryJobRepository(),
        equity_source=source,
        authentication=SimpleNamespace(clock=SimpleNamespace(now=lambda: AS_OF)),
    )
    job = enqueue_equity_enrichment(container, AS_OF)
    assert enqueue_equity_enrichment(container, AS_OF).id == job.id
    registry = JobHandlerRegistry()
    register_corporate_action_handlers(registry, container)
    handler = registry.get("tdx-equity-enrichment")
    result = handler(job)
    assert isinstance(result, JobContinuation) and job.payload["cursor"] == 1
    completed = handler(job)
    assert isinstance(completed, dict) and completed["completed"] == 1
    assert source.calls == 1
    # 历史缺口按周期自动复查，不会每次调度重新抓全历史。
    next_job = enqueue_equity_enrichment(container, AS_OF + timedelta(days=1))
    handler(next_job)
    assert source.calls == 1


def test_archive_snapshot_limits_coverage_even_when_imported_later():
    store = store_with_prices()
    prepare(store, [{**candidate(), "archive_snapshot_day": "2026-09-24"}], apply=True)
    book = CorporateActionBook(runtime_snapshot(store)["corporate_actions"])
    book.require_coverage("000001", date(2026, 9, 21), date(2026, 9, 24), AS_OF)
    with pytest.raises(StateConflictError, match="覆盖不足"):
        book.require_coverage("000001", date(2026, 9, 21), date(2026, 9, 25), AS_OF)
    with pytest.raises(ValueError, match="旧归档"):
        prepare(store, [{**candidate(), "archive_snapshot_day": "2026-09-23"}], apply=True)
    assert store.list_records(TDX_PRICE_DATASET)[0]["end_day"] == "2026-09-24"


def test_refresh_is_idempotent_and_source_revision_keeps_observed_version():
    from types import SimpleNamespace

    store = store_with_prices()
    prepare(store, [candidate()], apply=True)
    row = {
        "除权日": "2026-09-22",
        "股权登记日": "2026-09-21",
        "派息日": "2026-09-24",
        "实施方案公告日期": "2026-09-18",
        "派息比例": 10,
    }
    source = SimpleNamespace(fetch=lambda _symbol: [dict(row)])
    assert enrich_tdx_equity(store, source, "000001", AS_OF)["added"] == 1
    assert (
        enrich_tdx_equity(store, source, "000001", AS_OF + timedelta(days=1), refresh=True)["added"]
        == 0
    )
    row["派息比例"] = 12
    revised_at = AS_OF + timedelta(days=2)
    assert enrich_tdx_equity(store, source, "000001", revised_at, refresh=True)["added"] == 1
    book = CorporateActionBook(runtime_snapshot(store)["corporate_actions"])
    assert book.events("000001", AS_OF)[0].cash_per_share == 1
    assert book.events("000001", revised_at)[0].cash_per_share == Decimal("1.2")
    row["送股比例"] = 10
    assert enrich_tdx_equity(store, source, "000001", revised_at, refresh=True)["missing"]
    book = CorporateActionBook(runtime_snapshot(store)["corporate_actions"])
    with pytest.raises(StateConflictError, match="不兼容修订"):
        book.require_equity("000001", date(2026, 9, 22), revised_at)
    row.pop("送股比例")
    enrich_tdx_equity(store, source, "000001", revised_at, refresh=True)
    CorporateActionBook(runtime_snapshot(store)["corporate_actions"]).require_equity(
        "000001", date(2026, 9, 22), revised_at
    )


def test_published_equity_reaches_actual_cash_ledger_without_price_cash_substitution():
    from types import SimpleNamespace

    from easy_quant.domain.strategies.entities import Signal
    from tests.domain.test_corporate_actions import advance, session

    store = store_with_prices()
    prepare(store, [candidate()], apply=True)
    source = SimpleNamespace(
        fetch=lambda _symbol: [
            {
                "除权日": "2026-09-22",
                "股权登记日": "2026-09-21",
                "派息日": "2026-09-24",
                "实施方案公告日期": "2026-09-18",
                "派息比例": 12,
            }
        ]
    )
    enrich_tdx_equity(store, source, "000001", AS_OF)
    events = CorporateActionBook(runtime_snapshot(store)["corporate_actions"]).events(
        "000001", AS_OF
    )
    engine = session()
    advance(engine, 21, "10", [Signal("000001", "buy", Decimal(100), "test")], events)
    advance(engine, 22, None, events=events)
    assert engine.portfolio.cash == 0 and engine.portfolio.receivable_cash == 120
    advance(engine, 24, "9", events=events)
    assert engine.portfolio.cash == 120 and engine.portfolio.receivable_cash == 0
    engine.corporate_ledger.open(date(2026, 9, 24), engine.portfolio, events, engine.marks)
    assert engine.portfolio.cash == 120


def test_live_warrant_without_price_event_still_blocks_held_position():
    from types import SimpleNamespace

    from easy_quant.application.services.live_corporate_actions import pending_actions

    store = store_with_prices()
    prepare(store, [candidate(category=14)], apply=True)
    state = SimpleNamespace(
        instances={
            "live": {
                "started_at": "2026-09-21T00:00:00+08:00",
                "initial_cash": "1000",
                "initial_positions": {"000001": "100"},
            }
        },
        ledger=[],
    )
    with pytest.raises(StateConflictError, match="权证"):
        pending_actions(
            state, "live", CorporateActionBook(runtime_snapshot(store)["corporate_actions"]), AS_OF
        )


def test_failed_publication_keeps_current_generation_and_old_source_history():
    store = store_with_prices()
    prepare(store, [candidate()], apply=True)
    original = dict(store.list_records(TDX_PRICE_DATASET)[0])
    upsert = store.upsert_records

    def fail(dataset, rows, **kwargs):
        if dataset == TDX_PRICE_DATASET:
            raise RuntimeError("fixed publication failure")
        return upsert(dataset, rows, **kwargs)

    with patch.object(store, "upsert_records", side_effect=fail), pytest.raises(RuntimeError):
        prepare(store, [candidate(values=["20", "0", "0", "0"])], apply=True)
    assert store.list_records(TDX_PRICE_DATASET) == [original]
    assert len(store.list_records("tdx-price-history")) == 2


def test_chart_defaults_to_last_visible_bar_but_explicit_decision_still_checks_coverage():
    from tests.api.test_strategy_library import authenticated
    from tests.fakes.platform import make_test_container

    container = make_test_container(initialize_admin=True)
    container.market_data.upsert_instruments([{"symbol": "000001", "name": "fixture"}])
    container.market_data.upsert_bars(store_with_prices().list_bars())
    prepare(container.market_data, [candidate()], apply=True)
    client, _headers = authenticated(container)
    prefix = "/api/v1/admin/market-data/instruments/000001/daily-bars"
    response = client.get(prefix + "?adjustment=qfq")
    assert response.status_code == 200
    rows = response.get_json()["data"]
    assert rows[0]["close"] == 9
    assert rows[-1]["adjustment_anchor"] == "2026-09-24"
    response = client.get(prefix + "?adjustment=qfq&as_of=2026-09-26T00:00:00%2B00:00")
    assert response.status_code == 409
    assert client.get(prefix + "?adjustment=raw").get_json()["data"][0]["close"] == "10"


def test_host_rejects_legacy_dictionary_signal_for_excluded_symbol(fixed_now):
    from easy_quant.application.services.backtest_runtime import execute_backtest
    from easy_quant.domain.strategies.entities import StrategyDefinition, StrategyVersion
    from tests.fakes.platform import make_test_container

    container = make_test_container()
    container.market_data.upsert_bars(store_with_prices().list_bars())
    prepare(container.market_data, [candidate(category=15)], apply=True)
    source = """def before_market(c,p):
    return [{'symbol':'000001','action':'buy','quantity':100,'reason':'legacy'}]
def on_market(c,p):
    return []
def after_market(c,p):
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
            "start_day": "2026-09-22",
            "end_day": "2026-09-24",
            "initial_cash": "1000",
            "fee_rate": "0",
            "slippage_rate": "0",
        },
    }
    with pytest.raises(StateConflictError, match="策略信号"):
        execute_backtest(container, "b")

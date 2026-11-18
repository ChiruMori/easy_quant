import math
from copy import deepcopy

import pytest

from easy_quant.factors.financial import FORMULAS, raw_value
from easy_quant.strategy_api.context import RuntimeContext


def financial_records():
    records = {}
    fields = {
        "balance-sheets": {
            "total_assets": 1000,
            "accounts_receivable": 100,
            "total_liabilities": 400,
            "total_equity": 600,
            "current_assets": 300,
            "current_liabilities": 200,
            "inventory": 100,
        },
        "income-statements": {
            "eps": 2,
            "operating_revenue": 500,
            "net_profit": 100,
            "parent_net_profit": 80,
            "adjusted_net_profit": 60,
            "operating_cost": 200,
            "operating_profit": 120,
            "total_profit": 130,
        },
        "cash-flow-statements": {
            "operating_cash_flow": 150,
            "investing_cash_flow": -50,
            "financing_cash_flow": 20,
        },
    }
    for dataset, values in fields.items():
        records[dataset] = {}
        for symbol in ("a", "b", "000001", "000002", "000003"):
            records[dataset][symbol] = [
                {
                    "schema_version": "financial-v1",
                    "source": "eastmoney",
                    "report_period": period,
                    "available_at": available,
                    "currency": "CNY",
                    "statement_scope": "合并",
                    "period_basis": "时点" if dataset == "balance-sheets" else "年初至报告期累计",
                    **{key: str(value * multiplier) for key, value in values.items()},
                }
                for period, available, multiplier in (
                    ("2024-03-31", "2024-04-30T00:00:00+00:00", float("0.2")),
                    ("2024-06-30", "2024-08-01T00:00:00+00:00", float("0.4")),
                    ("2024-12-31", "2025-04-01T00:00:00+00:00", float(1)),
                    ("2025-03-31", "2025-04-30T00:00:00+00:00", float("0.3")),
                    ("2025-06-30", "2025-08-01T00:00:00+00:00", float("0.6")),
                )
            ]
    records["market-values"] = {
        s: [{"market_cap": "2000", "available_at": "2025-08-01T00:00:00+00:00"}] for s in ("a", "b")
    }
    return records


def runtime(records=None, at="2025-08-02T00:00:00+00:00"):
    return RuntimeContext(
        {"records": records if records is not None else financial_records(), "decision_at": at}
    )


@pytest.mark.parametrize("formula", FORMULAS, ids=lambda f: f.key)
def test_every_financial_factor_has_real_decimal_result(formula):
    result = runtime().factor(formula.key, symbol="a", symbols=["a", "b"])
    assert result["available"], result
    assert math.isfinite(result["value"])
    if formula.ranked:
        assert result["value"] == pytest.approx(float("0.75"), rel=1e-10, abs=1e-12)


def test_hand_calculated_ttm_quarter_annual_and_cash_flow_values():
    c = runtime()
    # 归母 TTM=48+80-32=96；半年末权益=360，不使用全年600或加权ROE。
    assert c.factor("roe_ttm", symbol="a")["value"] == pytest.approx(
        float(96) / 360, rel=1e-10, abs=1e-12
    )
    assert c.factor("roe_y", symbol="a")["value"] == pytest.approx(
        float(80) / 600, rel=1e-10, abs=1e-12
    )
    assert c.factor("quick_ratio", symbol="a")["value"] == pytest.approx(
        float(1), rel=1e-10, abs=1e-12
    )
    assert c.factor("earnings_to_price", symbol="a")["value"] == pytest.approx(
        float("0.048"), rel=1e-10, abs=1e-12
    )
    assert c.factor("ncf_to_market", symbol="a")["value"] == pytest.approx(
        float("0.072"), rel=1e-10, abs=1e-12
    )
    formula = next(f for f in FORMULAS if f.key == "opt_tpro")
    assert raw_value(c._factor_context, "a", formula) == pytest.approx(
        float(36) / 39, rel=1e-10, abs=1e-12
    )


def test_future_revision_and_late_old_period_do_not_replace_current_report():
    records = financial_records()
    rows = records["income-statements"]["a"]
    rows.append(
        {**rows[-1], "parent_net_profit": "9999", "available_at": "2026-01-01T00:00:00+00:00"}
    )
    rows.append({**rows[1], "parent_net_profit": "36", "available_at": "2025-08-02T00:00:00+00:00"})
    assert runtime(records).factor("roe_ttm", symbol="a")["value"] == pytest.approx(
        float(48 + 80 - 36) / 360, rel=1e-10, abs=1e-12
    )
    assert runtime(at="2025-07-01T00:00:00+00:00").factor("roe_ttm", symbol="a")[
        "value"
    ] == pytest.approx(float(88) / 180, rel=1e-10, abs=1e-12)


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("currency", "USD", "unsupported_financial_basis"),
        ("statement_scope", "母公司", "unsupported_financial_basis"),
        ("period_basis", "单季", "unsupported_financial_basis"),
        ("source", "sina", "mixed_financial_sources"),
        ("total_equity", "0", "non_positive_financial_denominator"),
        ("total_equity", "-1", "non_positive_financial_denominator"),
        ("total_equity", None, "missing_field"),
    ],
)
def test_invalid_report_does_not_fall_back_to_old_value(field, value, reason):
    records = financial_records()
    records["balance-sheets"]["a"][-1][field] = value
    assert runtime(records).factor("roe_ttm", symbol="a") == {"available": False, "reason": reason}


def test_missing_period_and_misaligned_statement_periods():
    records = financial_records()
    records["income-statements"]["a"].pop(1)
    assert runtime(records).factor("roe_ttm", symbol="a")["reason"] == "missing_financial_period"
    records = financial_records()
    records["balance-sheets"]["a"].pop()
    assert runtime(records).factor("roe_ttm", symbol="a")["reason"] == "unaligned_report_periods"


def test_rank_requires_real_universe_and_rejects_missing_members():
    c = runtime()
    assert not c.factor("roa_ttm", symbol="a")["available"]
    assert not c.factor("roa_ttm", symbol="a", symbols=["a", "a"])["available"]
    records = deepcopy(financial_records())
    records["income-statements"]["b"][-1]["net_profit"] = None
    assert not runtime(records).factor("roa_ttm", symbol="a", symbols=["a", "b"])["available"]
    records = financial_records()
    records["income-statements"]["b"][-1]["net_profit"] = "120"
    c = runtime(records)
    assert c.factor("roa_ttm", symbol="a", symbols=["a", "b"])["value"] == pytest.approx(
        float("0.5"), rel=1e-10, abs=1e-12
    )
    assert c.factor("roa_ttm", symbol="b", symbols=["a", "b"])["value"] == 1


def test_inventory_profit_growth_uses_report_quarters_and_prior_balance():
    records = financial_records()
    records["balance-sheets"]["a"][1]["inventory"] = "20"
    c = runtime(records)
    formula = next(f for f in FORMULAS if f.key == "np_to_inventory_yoy")
    # 当前(60-30)/60=.5，去年(40-20)/20=1，增长率=-.5。
    assert raw_value(c._factor_context, "a", formula) == pytest.approx(
        float("-0.5"), rel=1e-10, abs=1e-12
    )
    records["income-statements"]["a"].pop(0)
    assert not runtime(records).factor(formula.key, symbol="a", symbols=["a", "b"])["available"]


def test_future_market_cap_and_future_report_period_are_rejected():
    records = financial_records()
    records["market-values"]["a"].append(
        {"market_cap": "1", "available_at": "2026-01-01T00:00:00+00:00"}
    )
    assert runtime(records).factor("earnings_to_price", symbol="a")["value"] == pytest.approx(
        float(".048"), rel=1e-10, abs=1e-12
    )
    records["balance-sheets"]["a"][-1]["report_period"] = "2027-06-30"
    assert runtime(records).factor("de", symbol="a")["reason"] == "future_report_period"


def test_legacy_raw_revenue_projection_preserves_source_and_never_guesses_mixed_revenue():
    records = financial_records()
    for row in records["income-statements"]["a"]:
        revenue = row.pop("operating_revenue")
        row["revenue"] = "999999"
        row["raw_fields"] = {"OPERATE_INCOME": revenue, "TOTAL_OPERATE_INCOME": "999999"}
    c = runtime(records)
    assert raw_value(
        c._factor_context, "a", next(f for f in FORMULAS if f.key == "npm_y")
    ) == pytest.approx(0.2)
    assert raw_value(
        c._factor_context, "a", next(f for f in FORMULAS if f.key == "opm_ttm")
    ) == pytest.approx(0.24)
    projected = c.history("a", "income-statements")
    assert projected.iloc[-1]["operating_revenue"] == 300.0
    assert projected.iloc[-1]["total_operating_revenue"] == 999999.0
    assert projected.iloc[-1]["source"] == "eastmoney"
    records["income-statements"]["a"][-1]["raw_fields"] = {}
    assert (
        runtime(records).factor("npm_ttm", symbol="a", symbols=["a", "b"])["reason"]
        == "missing_field"
    )


def test_new_revenue_factors_follow_rank_and_single_quarter_sales_contract():
    c = runtime()
    for key in (
        "npm_q",
        "npm_y",
        "npm_ttm",
        "opm_y",
        "opm_ttm",
        "asset_turnover",
        "receivable_turnover",
        "equity_turnover",
    ):
        assert c.factor(key, symbol="a", symbols=["a", "b"])["value"] == 0.75
        assert not c.factor(key, symbol="a")["available"]
    # 2025Q2收入=(300-150)，除以当前可见市值2000。
    assert c.factor("sales_to_market", symbol="a")["value"] == pytest.approx(0.075)

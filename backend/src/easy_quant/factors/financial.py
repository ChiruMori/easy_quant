"""合并人民币报表的严格 PIT 组合。不使用供应商衍生指标或原始字段。"""

from dataclasses import dataclass
from datetime import date
from functools import partial

from easy_quant.factors.series import Unavailable, divide, number, percentile
from easy_quant.platform_library.financials import visible_versions

BALANCE = "balance-sheets"
INCOME = "income-statements"
CASH = "cash-flow-statements"


@dataclass(frozen=True)
class FinancialFormula:
    key: str
    numerator: tuple[str, ...]
    denominator: str
    basis: str = "ttm"
    ranked: bool = False
    category: str = "Quality"


# 流量字段先按 basis 组合；时点分母必须与流量报告期一致。
FORMULAS = (
    FinancialFormula("npm_q", ("net_profit",), "operating_revenue", "quarter", True),
    FinancialFormula("asset_turnover", ("operating_revenue",), "total_assets", ranked=True),
    FinancialFormula("npm_y", ("net_profit",), "operating_revenue", "annual", True),
    FinancialFormula("opm_y", ("operating_profit",), "operating_revenue", "annual", True),
    FinancialFormula("npm_ttm", ("net_profit",), "operating_revenue", ranked=True),
    FinancialFormula("opm_ttm", ("operating_profit",), "operating_revenue", ranked=True),
    FinancialFormula(
        "receivable_turnover", ("operating_revenue",), "accounts_receivable", ranked=True
    ),
    FinancialFormula("equity_turnover", ("operating_revenue",), "total_equity", ranked=True),
    FinancialFormula(
        "sales_to_market", ("operating_revenue",), "market_cap", "quarter", category="Value"
    ),
    FinancialFormula("eps_y", ("eps",), "one", "annual", True),
    FinancialFormula("np_to_inventory_yoy", ("net_profit",), "inventory", "quarter", True),
    FinancialFormula(
        "market_value_leverage",
        ("market_cap", "-total_liabilities", "current_liabilities"),
        "market_cap",
        "point",
        True,
    ),
    FinancialFormula("debt_asset_ratio", ("total_liabilities",), "total_assets", "annual"),
    FinancialFormula("de", ("total_liabilities",), "total_equity", "point"),
    FinancialFormula("financial_leverage", ("total_assets",), "total_equity", "point", True),
    FinancialFormula("current_ratio", ("current_assets",), "current_liabilities", "annual"),
    FinancialFormula(
        "quick_ratio", ("current_assets", "-inventory"), "current_liabilities", "annual"
    ),
    FinancialFormula("roe_y", ("parent_net_profit",), "total_equity", "annual"),
    FinancialFormula("roe_ttm", ("parent_net_profit",), "total_equity"),
    FinancialFormula("roa_y", ("net_profit",), "total_assets", "annual", True),
    FinancialFormula("roa_q", ("net_profit",), "total_assets", "quarter", True),
    FinancialFormula("roa_ttm", ("net_profit",), "total_assets", "ttm", True),
    FinancialFormula("inventory_turnover", ("operating_cost",), "inventory", "ttm", True),
    FinancialFormula(
        "cash_profit_ratio", ("operating_cash_flow", "-net_profit"), "net_profit", "ttm", True
    ),
    FinancialFormula("opt_tpro", ("operating_profit",), "total_profit", "quarter", True),
    FinancialFormula("earnings_to_price", ("parent_net_profit",), "market_cap", category="Value"),
    FinancialFormula(
        "earnings_cut_to_market", ("adjusted_net_profit",), "market_cap", category="Value"
    ),
    FinancialFormula("ocf_to_market", ("operating_cash_flow",), "market_cap", category="Value"),
    FinancialFormula(
        "ncf_to_market",
        ("operating_cash_flow", "investing_cash_flow", "financing_cash_flow"),
        "market_cap",
        category="Value",
    ),
)

FIELDS = {
    BALANCE: {
        "accounts_receivable",
        "total_liabilities",
        "total_assets",
        "total_equity",
        "current_assets",
        "current_liabilities",
        "inventory",
    },
    INCOME: {
        "operating_revenue",
        "eps",
        "parent_net_profit",
        "net_profit",
        "operating_cost",
        "operating_profit",
        "total_profit",
        "adjusted_net_profit",
    },
    CASH: {"operating_cash_flow", "investing_cash_flow", "financing_cash_flow"},
}


def dataset_for(field):
    return next(dataset for dataset, fields in FIELDS.items() if field in fields)


def datasets_for(formula):
    fields = [field.removeprefix("-") for field in formula.numerator] + [formula.denominator]
    return tuple(
        sorted(
            {"market-values" if f == "market_cap" else dataset_for(f) for f in fields if f != "one"}
        )
    )


class Reports:
    def __init__(self, context, symbol, datasets, basis):
        self.rows = {}
        latest = []
        for dataset in datasets:
            if dataset == "market-values":
                continue
            rows = visible_versions(context.read(dataset, symbol))
            # 不忽略最新的非法币种/范围，也不回退到更老的完整报告。
            rows = [
                r
                for r in rows
                if basis != "annual" or str(r.get("report_period", "")).endswith("12-31")
            ]
            if not rows:
                raise Unavailable("missing_financial_report")
            self.rows[dataset] = rows
            latest.append(rows[-1])
        self.period = str(latest[0].get("report_period", ""))
        try:
            report_day = date.fromisoformat(self.period)
        except ValueError as error:
            raise Unavailable("unsupported_financial_period") from error
        if report_day > context.as_of.date():
            raise Unavailable("future_report_period")
        if any(str(r.get("report_period")) != self.period for r in latest):
            raise Unavailable("unaligned_report_periods")
        self.source = latest[0].get("source")
        if not self.source or any(r.get("source") != self.source for r in latest):
            raise Unavailable("mixed_financial_sources")

    def value(self, field, period):
        dataset = dataset_for(field)
        rows = [r for r in self.rows[dataset] if r.get("report_period") == period]
        if not rows:
            raise Unavailable("missing_financial_period")
        row = rows[-1]
        expected_basis = "时点" if dataset == BALANCE else "年初至报告期累计"
        if row.get("source") != self.source:
            raise Unavailable("mixed_financial_sources")
        if (
            row.get("currency") != "CNY"
            or row.get("statement_scope") != "合并"
            or row.get("period_basis") != expected_basis
        ):
            raise Unavailable("unsupported_financial_basis")
        return number(row.get(field))

    def amount(self, field, basis, period=None):
        period = period or self.period
        year, end = int(period[:4]), period[5:]
        if end not in {"03-31", "06-30", "09-30", "12-31"}:
            raise Unavailable("unsupported_financial_period")
        value = self.value(field, period)
        if dataset_for(field) == BALANCE or basis in {"annual", "point"}:
            return value
        if basis == "ttm":
            if end == "12-31":
                return value
            return (
                value
                + self.value(field, f"{year - 1}-12-31")
                - self.value(field, f"{year - 1}-{end}")
            )
        if end == "03-31":
            return value
        previous = {"06-30": "03-31", "09-30": "06-30", "12-31": "09-30"}[end]
        return value - self.value(field, f"{year}-{previous}")


def raw_value(context, symbol, formula):
    reports = Reports(context, symbol, datasets_for(formula), formula.basis)

    def amount(field):
        if field == "one":
            return float(1)
        if field != "market_cap":
            return reports.amount(field, formula.basis)
        rows = context.read("market-values", symbol)
        if not rows:
            raise Unavailable("missing_market_value")
        value = number(max(rows, key=lambda r: r["available_at"]).get("market_cap"))
        if value <= 0:
            raise Unavailable("non_positive_market_value")
        return value

    numerator = sum(
        ((-1 if f.startswith("-") else 1) * amount(f.removeprefix("-")) for f in formula.numerator),
        float(0),
    )
    denominator = amount(formula.denominator)
    if denominator <= 0:
        raise Unavailable("non_positive_financial_denominator")
    value = divide(numerator, denominator)
    if formula.key == "np_to_inventory_yoy":
        prior = f"{int(reports.period[:4]) - 1}{reports.period[4:]}"
        inventory = reports.amount("inventory", "point", prior)
        if inventory <= 0:
            raise Unavailable("non_positive_financial_denominator")
        previous = divide(reports.amount("net_profit", "quarter", prior), inventory)
        if previous <= 0:
            raise Unavailable("non_positive_financial_denominator")
        return divide(value, previous) - 1
    return value


def calculate(context, parameters, *, formula):
    symbol = str(parameters["symbol"])
    if not formula.ranked:
        return raw_value(context, symbol, formula)
    symbols = parameters.get("symbols")
    if not isinstance(symbols, list) or symbol not in symbols or len(set(symbols)) < 2:
        raise Unavailable("explicit_universe_at_least_2_required")
    symbols = sorted(set(symbols))
    if len(symbols) > 500:
        raise Unavailable("universe_limit_500")
    # 不能把缺失成员移除后输出一个改变了股票池含义的排名。
    values = {s: raw_value(context, s, formula) for s in symbols}
    return percentile(values[symbol], list(values.values()))


def references():
    from easy_quant.factors.reference import Reference

    result = []
    for formula in FORMULAS:
        numerator = "+".join(formula.numerator).replace("+-", "-")
        expression = f"({numerator}) / {formula.denominator}"
        if formula.key == "np_to_inventory_yoy":
            expression = "(NetProfit_Q / Inventory) / (上年同季NetProfit_Q / 上年同季Inventory) - 1"
        if formula.ranked:
            expression = f"CrossSectionalRank({expression})"
        result.append(
            Reference(
                formula.key,
                formula.category,
                1,
                partial(calculate, formula=formula),
                f"计算逻辑：{expression}；流量采用{formula.basis}口径，时点分母取同报告期末值。\n"
                "结果含义：比率为小数，不乘100；截面排名采用平均并列秩/N，越高表示原始比率越高，不保证未来收益。\n"
                "数据约束：合并CNY报表，同一来源、相同报告期；TTM=当期累计+上年全年-上年同期；单季=累计差分。年度项只取最新可见年报。"
                "市值取决策时点最新可见快照，不推算为当日市值。分母非正、缺期或任何股票池成员缺失均不可用。",
                datasets_for(formula),
            )
        )
    return tuple(result)

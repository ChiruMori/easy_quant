"""共享基本面数据集及平台字段契约；不含供应商字段或外部 I/O。"""

FINANCIAL_DATASETS = {
    "balance-sheets": "资产负债表",
    "income-statements": "利润表",
    "cash-flow-statements": "现金流量表",
    "financial-indicators": "主要财务指标",
    "company-profiles": "公司概况",
    "dividend-plans": "分红送配",
    "shareholder-counts": "股东户数与股本",
    "business-compositions": "主营构成",
}

# 百分比统一为百分数，例如 12.5 表示 12.5%；金额统一为报告币种元。
FIELD_METADATA = {
    "total_assets": ("资产总计", "元"),
    "total_liabilities": ("负债合计", "元"),
    "total_equity": ("股东权益合计", "元"),
    "parent_equity": ("归母股东权益", "元"),
    "cash": ("货币资金", "元"),
    "current_assets": ("流动资产", "元"),
    "current_liabilities": ("流动负债", "元"),
    "inventory": ("存货", "元"),
    "accounts_receivable": ("应收账款", "元"),
    "goodwill": ("商誉", "元"),
    "revenue": ("营业总收入", "元"),
    "operating_cost": ("营业成本", "元"),
    "operating_profit": ("营业利润", "元"),
    "total_profit": ("利润总额", "元"),
    "net_profit": ("净利润", "元"),
    "parent_net_profit": ("归母净利润", "元"),
    "adjusted_net_profit": ("扣非归母净利润", "元"),
    "operating_cash_flow": ("经营活动现金净额", "元"),
    "investing_cash_flow": ("投资活动现金净额", "元"),
    "financing_cash_flow": ("筹资活动现金净额", "元"),
    "cash_increase": ("现金及等价物净增加额", "元"),
    "ending_cash": ("期末现金及等价物余额", "元"),
    "eps": ("基本每股收益", "元/股"),
    "diluted_eps": ("稀释每股收益", "元/股"),
    "book_value_per_share": ("每股净资产", "元/股"),
    "cash_flow_per_share": ("每股经营现金流", "元/股"),
    "roe": ("加权净资产收益率", "%"),
    "roa": ("总资产收益率", "%"),
    "gross_margin": ("毛利率", "%"),
    "net_margin": ("净利率", "%"),
    "debt_ratio": ("资产负债率", "%"),
    "revenue_growth": ("营业收入同比", "%"),
    "profit_growth": ("归母净利润同比", "%"),
    "current_ratio": ("流动比率", "倍"),
    "quick_ratio": ("速动比率", "倍"),
    "holder_count": ("股东户数", "户"),
    "holder_change_ratio": ("股东户数增减", "%"),
    "total_shares": ("总股本", "股"),
    "average_shares": ("户均持股", "股/户"),
    "cash_per_ten_shares": ("每10股现金分红（税前）", "元/10股"),
    "bonus_per_ten_shares": ("每10股送股", "股/10股"),
    "transfer_per_ten_shares": ("每10股转增", "股/10股"),
    "dividend_yield": ("股息率", "%"),
    "business_revenue": ("主营收入", "元"),
    "business_cost": ("主营成本", "元"),
    "business_profit": ("主营利润", "元"),
    "revenue_ratio": ("收入占比", "%"),
    "cost_ratio": ("成本占比", "%"),
    "profit_ratio": ("利润占比", "%"),
    "registered_capital": ("注册资本", "元"),
    "employee_count": ("员工人数", "人"),
}


def report_kind(period: str) -> str:
    return {"03-31": "一季报", "06-30": "中报", "09-30": "三季报", "12-31": "年报"}.get(
        period[5:], "其他"
    )

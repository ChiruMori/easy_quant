"""从冻结的公开条目基线和当前注册表导出当前清单、逐项限制。"""

import json
from pathlib import Path

from easy_quant.factors.reference import references

ROOT = Path(__file__).resolve().parents[2]


def limitations(item):
    key = item["name"]
    original = item["required_changes"].removeprefix("F1/F2：补齐 ")
    original = original.split("；以公告/修订可获知时间")[0]
    if item["category"] == "Liquidity":
        return (
            "股东户数快照的total_shares混合TOTAL_A_SHARES与TOTAL_SHARES，不能确认历史A股/流通股数量和生效日期；不能拿当前股本回填历史。",
            "拆分A股、总股本、流通股本及生效日/可获知时间，接公司行为形成PIT股本序列；并澄清名称21/42日与正文121/221日等窗口冲突。",
        )
    if key in {"eps_q", "eps_ttm", "eaa", "eap", "peg_252d", "pegh5"}:
        return (
            "当前基本EPS是累计加权股数口径，季度间分母可变化；直接累计差分或拼接四季EPS不能保证正确。",
            f"补充原生单季/TTM EPS或可重建的加权股数及送转追溯规则；明确并验证 {original}。",
        )
    if key in {
        "npm_tsh",
        "gpm_q",
        "gpm_y",
        "roe_ttm_lag63d",
        "small_cap_reversal_21d",
        "quality_composite",
        "np_ttm_qoq",
        "asset_growth_qoq",
    }:
        return (
            "公开名称/文字与算式期别、分母或滞后定义不一致，或股票池/缺失过滤规则未定义；不猜测并注册同名近似值。",
            f"先确认唯一公式、期别、滞后和缺失语义；再满足 {original}。",
        )
    revenue_keys = {
        "gpm_ttm",
        "npm_q",
        "asset_turnover",
        "delta_opm",
        "delta_npm",
        "npm_y",
        "opm_y",
        "delta_gpm",
        "gpm_qoq",
        "npm_ttm",
        "opm_ttm",
        "receivable_turnover",
        "npm_q_qoq",
        "npm_ttm_qoq",
        "delta_asset_turnover",
        "equity_turnover",
        "sales_to_market",
        "gross_margin_qoq",
        "yoy_revenue",
        "sa",
        "ar_ap_to_revenue",
        "fixed_asset_turnover",
    }
    if key in revenue_keys:
        return (
            "规范化revenue字段混合营业总收入与营业收入，金融行业尤其不保证可与营业成本配比；部分条目还缺固定资产/预收预付或历史滞后。",
            "先分离operating_revenue与total_operating_revenue，"
            f"重归一化已有原始报表并核验行业口径；再补齐 {original}。",
        )
    if key.startswith("delta_") or key in {
        "pa",
        "yoy_net_profit",
        "yoy_ocf",
        "yoy_roa",
        "yoy_net_asset",
        "yoy_roe",
        "yoy_total_asset",
        "etp5",
    }:
        return (
            "当前PIT报表可见性已支持，但尚未建立覆盖所需滞后区间的统一交易日日历财务序列；保守采集时间使新采历史报告在过去不可见，不能据报告期倒灌或用个股缺日网格代替交易日。",
            "建立交易所日历上的逐决策日PIT投影、历史版本覆盖诊断和修订回归；"
            f"明确期别后验证 {original}。",
        )
    if key == "dividend_yield_3y_avg":
        return (
            "已接入分红方案但方案不等于实际派发，且送转调整和完整实施状态未形成可计算事件流。",
            "补足实际实施/撤销状态、每股实派金额、除权日、股数调整与公告版本；按735交易日事件窗口计算。",
        )
    return (
        "现有三表/PIT已接入，但该公式需要的独立科目仍未规范化，不能用净额、近似值或PE/PB替代。",
        "增加供应商无关的科目映射、单位/累计期别/来源版本测试，重归一化原始报表；"
        f"逐项补齐 {original}。",
    )


def main():
    baseline = json.loads(
        (ROOT / "specs/036-reference-factor-catalog/inventory.json").read_text(encoding="utf-8")
    )
    implemented = {r.key: r for r in references()}
    for item in baseline:
        if item["name"] in implemented:
            ref = implemented[item["name"]]
            item.clear()
            item.update(
                category=ref.category,
                name=ref.key,
                status="implemented",
                history=ref.history,
                datasets=ref.datasets,
            )
        else:
            item["reason"], item["required_changes"] = limitations(item)
    (ROOT / "docs/factor-inventory.json").write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# 因子支持限制",
        "",
        f"截至2026-11-17，公开{len(baseline)}项中{len(implemented)}项支持、"
        f"{len(baseline) - len(implemented)}项未注册。"
        "逐项状态见 [factor-inventory.json](factor-inventory.json)。"
        "本页只说明当前缺口及启用条件，不承诺未来交付。",
        "",
        "已接入财报不等于所有历史时点都有可见报表：新采集的旧报告仍按保守可获知时间过滤。正式回测/实盘缺数据返回不可用，不补造历史。",
        "",
        "| 类别 | Key | 当前原因 | 启用条件 |",
        "| --- | --- | --- | --- |",
    ]
    lines.extend(
        f"| {i['category']} | `{i['name']}` | {i['reason']} | {i['required_changes']} |"
        for i in baseline
        if i["status"] == "blocked"
    )
    lines.extend(
        [
            "",
            "公开摘要另有70个Alpha101未列出公式；取得可核验的完整公式、窗口与截面/中性化定义前不注册。项目名见[历史公开条目核对](../specs/036-reference-factor-catalog/unsupported.md#未公开的alpha101条目)。",
            "",
        ]
    )
    (ROOT / "docs/因子支持限制.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()

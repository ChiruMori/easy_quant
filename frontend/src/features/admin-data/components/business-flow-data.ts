import Decimal from "decimal.js"

import type { FundamentalRecord } from "../api"
import { chartNumber } from "./report-data"

export const businessFields = [
  { key: "business_revenue", label: "主营收入", color: "var(--chart-1)" },
  { key: "business_cost", label: "主营成本", color: "var(--chart-2)" },
  { key: "business_profit", label: "主营利润", color: "var(--chart-3)" },
] as const

const Amount = Decimal.clone({ precision: 50 })

// 输入已按单一报告期、来源和分类筛选；只在展示边界转为浮点。
export function businessFlow(rows: FundamentalRecord[]) {
  const points = rows.map((row) => ({
    id: row.record_key,
    name: String(row.item_name ?? "未命名项目"),
    business_revenue: chartNumber(row.business_revenue),
    business_cost: chartNumber(row.business_cost),
    business_profit: chartNumber(row.business_profit),
  }))
  const empty = (reason: string) => ({ points, flow: null, reason })
  if (!rows.length) return empty("所选报告暂无已披露构成，缺失值不补零。")
  if (
    rows.length > 1 &&
    rows.some((row) =>
      /^(合计|总计|主营业务合计|主营业务收入合计|营业收入合计)$/.test(
        String(row.item_name ?? "").trim(),
      ),
    )
  )
    return empty("包含汇总与明细项目，使用三指标对比图，避免重复汇总。")
  if (rows.some((row) => businessFields.some(({ key }) => chartNumber(row[key]) === null)))
    return empty("存在缺失指标，使用三指标对比图保留空缺，不推算收入、成本或利润。")
  const amounts = rows.map((row) => businessFields.map(({ key }) => new Amount(String(row[key]))))
  if (amounts.some((values) => values.some((value) => value.lt(0))))
    return empty("包含亏损或负值，使用三指标对比图保留正负方向，不转换为正向流量。")
  if (amounts.some(([revenue, cost, profit]) => !revenue.eq(cost.plus(profit))))
    return empty("来源收入与成本、利润之和不一致，使用三指标对比图，不补造差额。")
  if (new Set(rows.map((row) => row.currency ?? "CNY")).size > 1)
    return empty("存在不同报告币种，不合并为收支流量；请在数值表核对币种。")
  const totals = businessFields.map((_, index) =>
    amounts.reduce((total, values) => total.plus(values[index]), new Amount(0)),
  )
  if (totals[0].isZero()) return empty("收入均为零，使用三指标对比图和数值表展示真实零值。")
  if (totals.some((value) => chartNumber(value) === null))
    return empty("汇总金额超出图表数值范围，请查看各项目数值。")
  const positive = points.filter((_, index) => amounts[index][0].gt(0))
  const nodes = positive.map((point) => ({ name: point.name, kind: "item" }))
  const income = nodes.length
  nodes.push({ name: "主营收入合计", kind: "income" })
  const links = positive.map((point, index) => ({
    source: index,
    target: income,
    value: point.business_revenue as number,
  }))
  for (const [index, kind] of [
    [1, "cost"],
    [2, "profit"],
  ] as const) {
    if (totals[index].isZero()) continue
    const target = nodes.length
    nodes.push({ name: `${businessFields[index].label}合计`, kind })
    links.push({ source: income, target, value: chartNumber(totals[index])! })
  }
  return {
    points,
    flow: { nodes, links },
    reason: "零值项目保留在数值表；仅汇总当前分类已披露项目。",
  }
}

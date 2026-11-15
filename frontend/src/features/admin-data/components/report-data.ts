import Decimal from "decimal.js"

import type { FundamentalRecord } from "../api"

export const reportMetrics = {
  parent_net_profit: {
    label: "归母净利润",
    dataset: "income-statements",
    unit: "亿元",
    scale: 1e8,
  },
  revenue: { label: "营业收入", dataset: "income-statements", unit: "亿元", scale: 1e8 },
  adjusted_net_profit: {
    label: "扣非归母净利润",
    dataset: "financial-indicators",
    unit: "亿元",
    scale: 1e8,
  },
  roe: { label: "净资产收益率", dataset: "financial-indicators", unit: "%", scale: 1 },
  gross_margin: { label: "毛利率", dataset: "financial-indicators", unit: "%", scale: 1 },
  eps: { label: "每股收益", dataset: "financial-indicators", unit: "元/股", scale: 1 },
  total_assets: { label: "资产总计", dataset: "balance-sheets", unit: "亿元", scale: 1e8 },
  operating_cash_flow: {
    label: "经营现金净额",
    dataset: "cash-flow-statements",
    unit: "亿元",
    scale: 1e8,
  },
}

export function chartNumber(value: unknown, scale = 1e8): number | null {
  if (value === null || value === undefined || value === "") return null
  try {
    const number = new Decimal(String(value)).div(scale)
    return number.isFinite() && Number.isFinite(number.toNumber()) ? number.toNumber() : null
  } catch {
    return null
  }
}

export function reportPeriods(asOf: string): string[] {
  const day = asOf.slice(0, 10)
  const year = Number(day.slice(0, 4))
  return Array.from({ length: 6 }, (_, offset) => year - 5 + offset).flatMap((year) =>
    ["03-31", "06-30", "09-30", "12-31"]
      .map((suffix) => `${year}-${suffix}`)
      .filter((period) => period < day),
  )
}

export function reportPoints(
  rows: FundamentalRecord[],
  periods: string[],
  metric: string,
  scale: number,
) {
  const reports = new Map(
    rows
      .filter((row) => !row.statement_scope || row.statement_scope === "合并")
      .map((row) => [row.report_period, row]),
  )
  return periods.map((period) => ({
    period,
    value: chartNumber(reports.get(period)?.[metric], scale),
  }))
}

export const reportTypes = [
  { key: "q1", suffix: "03-31", label: "一季报", color: "var(--chart-1)" },
  { key: "half", suffix: "06-30", label: "中报", color: "var(--chart-2)" },
  { key: "q3", suffix: "09-30", label: "三季报", color: "var(--chart-3)" },
  { key: "annual", suffix: "12-31", label: "年报", color: "var(--chart-4)" },
] as const

export function reportYearGroups(points: { period: string; value: number | null }[]) {
  const years = new Map<
    string,
    {
      year: string
      q1: number | null
      half: number | null
      q3: number | null
      annual: number | null
    }
  >()
  for (const point of points) {
    const type = reportTypes.find(({ suffix }) => point.period.endsWith(suffix))
    if (!type) continue
    const year = point.period.slice(0, 4)
    const group = years.get(year) ?? { year, q1: null, half: null, q3: null, annual: null }
    group[type.key] = point.value
    years.set(year, group)
  }
  return [...years.values()].sort((a, b) => a.year.localeCompare(b.year))
}

export function reportCoverage(
  rows: FundamentalRecord[],
  period: string,
  fields: string[],
  state: "ready" | "loading" | "error",
) {
  if (state === "loading") return "加载中"
  if (state === "error") return "状态未知"
  const current = rows.filter((row) => row.report_period === period)
  if (!current.length) return "未采集"
  const values = current.flatMap((row) => fields.map((field) => chartNumber(row[field])))
  if (values.every((value) => value === null)) return "指标缺失"
  return values.some((value) => value === null) ? "部分缺失" : "已有数据"
}

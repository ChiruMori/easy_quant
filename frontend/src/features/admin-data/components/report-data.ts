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

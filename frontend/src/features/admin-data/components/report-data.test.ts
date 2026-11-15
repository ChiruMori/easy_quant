import { describe, expect, it } from "vitest"

import {
  chartNumber,
  reportCoverage,
  reportPeriods,
  reportPoints,
  reportYearGroups,
} from "./report-data"

describe("财报图表时间与缺失语义", () => {
  it("全部报告按年并列累计值，不相加，缺失不补零，保留真实零和负值", () => {
    expect(
      reportYearGroups([
        { period: "2025-12-31", value: 10 },
        { period: "2024-12-31", value: -2 },
        { period: "2025-03-31", value: 0 },
        { period: "2025-06-30", value: 4 },
        { period: "2025-09-30", value: null },
      ]),
    ).toEqual([
      { year: "2024", q1: null, half: null, q3: null, annual: -2 },
      { year: "2025", q1: 0, half: 4, q3: null, annual: 10 },
    ])
    const current = reportYearGroups(
      reportPoints([], reportPeriods("2026-11-14"), "revenue", 1e8),
    ).at(-1)
    expect(current).toEqual({ year: "2026", q1: null, half: null, q3: null, annual: null })
  })
  it("缺失不转零，真实零和负利润仍展示", () => {
    expect(chartNumber(null)).toBeNull()
    expect(chartNumber("NaN")).toBeNull()
    expect(chartNumber("0")).toBe(0)
    expect(chartNumber("-123456789.123456789")).toBeCloseTo(-1.23456789123456789)
  })
  it("报告期不超出当前日期，不混加季度或母公司口径", () => {
    const periods = reportPeriods("2026-11-14T00:00:00+08:00")
    expect(periods).toContain("2026-09-30")
    expect(periods).not.toContain("2026-12-31")
    expect(
      reportPoints(
        [
          {
            record_key: "1",
            available_at: "2026-04-01",
            report_period: "2025-12-31",
            statement_scope: "合并",
            revenue: "100000000",
          },
          {
            record_key: "2",
            available_at: "2026-04-01",
            report_period: "2025-12-31",
            statement_scope: "母公司",
            revenue: "99900000000",
          },
        ],
        ["2024-12-31", "2025-12-31"],
        "revenue",
        1e8,
      ),
    ).toEqual([
      { period: "2024-12-31", value: null },
      { period: "2025-12-31", value: 1 },
    ])
  })
  it("补采覆盖区分已有报表、所选指标缺失和未知状态，零值有效", () => {
    const rows = [
      {
        record_key: "r",
        available_at: "2026-01-01T00:00:00+08:00",
        report_period: "2025-12-31",
        revenue: "0",
      },
    ]
    expect(reportCoverage(rows, "2025-12-31", ["revenue"], "ready")).toBe("已有数据")
    expect(reportCoverage(rows, "2025-12-31", ["parent_net_profit"], "ready")).toBe("指标缺失")
    expect(reportCoverage(rows, "2024-12-31", ["revenue"], "ready")).toBe("未采集")
    expect(reportCoverage(rows, "2024-12-31", ["revenue"], "loading")).toBe("加载中")
    expect(reportCoverage(rows, "2024-12-31", ["revenue"], "error")).toBe("状态未知")
    expect(reportCoverage(rows, "2025-12-31", ["revenue", "business_cost"], "ready")).toBe(
      "部分缺失",
    )
  })
})

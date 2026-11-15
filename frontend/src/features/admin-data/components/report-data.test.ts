import { describe, expect, it } from "vitest"

import { chartNumber, reportPeriods, reportPoints } from "./report-data"

describe("财报图表时间与缺失语义", () => {
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
})

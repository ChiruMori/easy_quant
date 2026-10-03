import { describe, expect, it } from "vitest"

import { aggregateCandles } from "./candles"
import type { DailyBar } from "./types"

const bars: DailyBar[] = [
  {
    symbol: "000001",
    trading_day: "2025-12-31",
    open: "10.10",
    high: "10.50",
    low: "9.90",
    close: "10.20",
    volume: "1",
  },
  {
    symbol: "000001",
    trading_day: "2026-01-02",
    open: "10.20",
    high: "11.10",
    low: "10.00",
    close: "10.90",
    volume: "1",
  },
  {
    symbol: "000001",
    trading_day: "2026-01-05",
    open: "10.90",
    high: "11.00",
    low: "10.30",
    close: "10.50",
    volume: "1",
  },
]

describe("A 股 K 线周期", () => {
  it("日线按交易日排序且不修改原始数据", () => {
    const reversed = [...bars].reverse()
    expect(aggregateCandles(reversed, "day").map((bar) => bar.trading_day)).toEqual([
      "2025-12-31",
      "2026-01-02",
      "2026-01-05",
    ])
    expect(reversed[0].trading_day).toBe("2026-01-05")
  })

  it("周线跨年按同一自然周聚合，月线按月聚合", () => {
    expect(aggregateCandles(bars, "week")).toEqual([
      { trading_day: "2026-01-02", open: "10.10", high: "11.1", low: "9.9", close: "10.90" },
      { trading_day: "2026-01-05", open: "10.90", high: "11.00", low: "10.30", close: "10.50" },
    ])
    expect(aggregateCandles(bars, "month")).toHaveLength(2)
    expect(aggregateCandles(bars, "month")[1]).toEqual({
      trading_day: "2026-01-05",
      open: "10.20",
      high: "11.1",
      low: "10",
      close: "10.50",
    })
  })
})

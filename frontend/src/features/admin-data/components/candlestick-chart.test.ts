import { describe, expect, it } from "vitest"

import { candlestickOption, formatCandleTooltip } from "./candlestick-chart"

describe("A 股 K 线配置", () => {
  it("MA5 从所选区间第五个交易日起绘制，使用历史五日收盘且不泄漏后续值", () => {
    const bars = ["0.1", "0.2", "0.3", "0.4", "0.5", "100"].map((close, index) => ({
      trading_day: `2026-09-${21 + index}`,
      open: close,
      close,
      low: close,
      high: close,
    }))
    const option = candlestickOption(bars, "red", "green")
    const series = option.series as Array<{
      type: string
      name: string
      data: Array<number | null>
      connectNulls: boolean
    }>
    expect(series[1].data).toEqual([null, null, null, null, 0.3, 20.28])
    expect(series[1].name).toBe("MA5（5日）")
    expect(series[1].connectNulls).toBe(false)
    const formatter = (option.tooltip as { formatter: (params: unknown) => string }).formatter
    expect(formatter([{ dataIndex: 3 }])).not.toContain("MA5")
    expect(formatter([{ dataIndex: 4 }])).toContain("MA5（5日）：0.30")
    const shorter = candlestickOption(bars.slice(0, 4), "red", "green").series as typeof series
    expect(shorter[1].data).toEqual([null, null, null, null])
    const weekly = candlestickOption(bars, "red", "green", "week").series as typeof series
    expect(weekly[1].name).toBe("MA5（5周）")
  })
  it("使用红涨绿跌 OHLC 和可拖动、缩放的数据窗口", () => {
    const option = candlestickOption(
      [{ trading_day: "2026-09-29", open: "10", close: "11", low: "9", high: "12" }],
      "#d92d36",
      "#15935b",
    )
    const series = JSON.stringify(option.series)
    const zoom = JSON.stringify(option.dataZoom)
    expect(series).toContain('"type":"candlestick"')
    expect(series).toContain('"data":[[10,11,9,12]]')
    expect(series).toContain('"color":"#d92d36"')
    expect(series).toContain('"color0":"#15935b"')
    expect(zoom).toContain('"type":"inside"')
    expect(zoom).toContain('"moveOnMouseMove":true')
    expect(zoom).toContain('"type":"slider"')
  })

  it("数据提示使用中文字段名称", () => {
    const bar = { trading_day: "2026-09-29", open: "10", close: "11", low: "9", high: "12" }
    expect(formatCandleTooltip(bar)).toBe(
      "日期：2026-09-29<br/>开盘：10<br/>收盘：11<br/>最低：9<br/>最高：12",
    )
    const option = candlestickOption([bar], "#d92d36", "#15935b")
    const tooltip = option.tooltip as { formatter: (params: unknown) => string }
    expect(tooltip.formatter([{ dataIndex: 0 }])).toContain("开盘：10")
    expect(JSON.stringify(option.series)).toContain('"name":"K 线"')
  })
})

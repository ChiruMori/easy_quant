import { describe, expect, it } from "vitest"

import { candlestickOption } from "./candlestick-chart"

describe("A 股 K 线配置", () => {
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
})

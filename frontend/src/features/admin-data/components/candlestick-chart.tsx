import type { EChartsOption } from "echarts"
import { CandlestickChart as EChartsCandlestickChart, LineChart } from "echarts/charts"
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from "echarts/components"
import { init, use as registerModules } from "echarts/core"
import { CanvasRenderer } from "echarts/renderers"
import { useEffect, useRef } from "react"

import { type CandleBar, type CandlePeriod, movingAverage } from "../candles"

registerModules([
  EChartsCandlestickChart,
  LineChart,
  LegendComponent,
  DataZoomComponent,
  GridComponent,
  TooltipComponent,
  CanvasRenderer,
])

export function formatCandleTooltip(
  bar: CandleBar,
  average?: number | null,
  label = "MA5（5日）",
): string {
  const day = bar.trading_day.replace(/[^0-9-]/g, "")
  return [
    `日期：${day}`,
    `开盘：${Number(bar.open)}`,
    `收盘：${Number(bar.close)}`,
    `最低：${Number(bar.low)}`,
    `最高：${Number(bar.high)}`,
    ...(average === null || average === undefined ? [] : [`${label}：${average.toFixed(2)}`]),
  ].join("<br/>")
}

export function candlestickOption(
  bars: CandleBar[],
  upColor: string,
  downColor: string,
  period: CandlePeriod = "day",
): EChartsOption {
  const average = movingAverage(bars)
  const label = `MA5（5${period === "day" ? "日" : period === "week" ? "周" : "月"}）`
  return {
    animation: false,
    grid: { left: 68, right: 24, top: 40, bottom: 84 },
    legend: { data: ["K 线", label], top: 0 },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross" },
      formatter: (params: unknown) => {
        const item = Array.isArray(params) ? params[0] : params
        const index =
          item && typeof item === "object" && "dataIndex" in item ? Number(item.dataIndex) : -1
        const bar = bars[index]
        return bar ? formatCandleTooltip(bar, average[index], label) : ""
      },
    },
    xAxis: { type: "category", data: bars.map((bar) => bar.trading_day), boundaryGap: true },
    yAxis: { type: "value", scale: true },
    dataZoom: [
      {
        type: "inside",
        start: Math.max(0, (1 - 80 / bars.length) * 100),
        end: 100,
        zoomOnMouseWheel: true,
        moveOnMouseMove: true,
      },
      {
        type: "slider",
        start: Math.max(0, (1 - 80 / bars.length) * 100),
        end: 100,
        bottom: 24,
      },
    ],
    series: [
      {
        name: "K 线",
        type: "candlestick",
        data: bars.map((bar) => [bar.open, bar.close, bar.low, bar.high].map(Number)),
        itemStyle: {
          color: upColor,
          color0: downColor,
          borderColor: upColor,
          borderColor0: downColor,
        },
      },
      {
        name: label,
        type: "line",
        data: average,
        showSymbol: false,
        connectNulls: false,
        lineStyle: { width: 1.5 },
        itemStyle: { color: "#f59e0b" },
      },
    ],
  }
}

export function CandlestickChart({
  bars,
  period = "day",
}: {
  bars: CandleBar[]
  period?: CandlePeriod
}) {
  const element = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!element.current) return
    const style = getComputedStyle(document.documentElement)
    const upColor = style.getPropertyValue("--market-up").trim() || "#d92d36"
    const downColor = style.getPropertyValue("--market-down").trim() || "#15935b"
    const chart = init(element.current)
    chart.setOption(candlestickOption(bars, upColor, downColor, period))
    const observer = new ResizeObserver(() => chart.resize())
    observer.observe(element.current)
    return () => {
      observer.disconnect()
      chart.dispose()
    }
  }, [bars, period])

  return (
    <div ref={element} role="img" aria-label="可缩放和拖动的 K 线图" className="h-[420px] w-full" />
  )
}

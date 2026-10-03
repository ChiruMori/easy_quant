import type { EChartsOption } from "echarts"
import { CandlestickChart as EChartsCandlestickChart } from "echarts/charts"
import { DataZoomComponent, GridComponent, TooltipComponent } from "echarts/components"
import { init, use as registerModules } from "echarts/core"
import { CanvasRenderer } from "echarts/renderers"
import { useEffect, useRef } from "react"

import type { CandleBar } from "../candles"

registerModules([
  EChartsCandlestickChart,
  DataZoomComponent,
  GridComponent,
  TooltipComponent,
  CanvasRenderer,
])

export function candlestickOption(
  bars: CandleBar[],
  upColor: string,
  downColor: string,
): EChartsOption {
  return {
    animation: false,
    grid: { left: 68, right: 24, top: 24, bottom: 84 },
    tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
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
        name: "OHLC",
        type: "candlestick",
        data: bars.map((bar) => [bar.open, bar.close, bar.low, bar.high].map(Number)),
        itemStyle: {
          color: upColor,
          color0: downColor,
          borderColor: upColor,
          borderColor0: downColor,
        },
      },
    ],
  }
}

export function CandlestickChart({ bars }: { bars: CandleBar[] }) {
  const element = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!element.current) return
    const style = getComputedStyle(document.documentElement)
    const upColor = style.getPropertyValue("--market-up").trim() || "#d92d36"
    const downColor = style.getPropertyValue("--market-down").trim() || "#15935b"
    const chart = init(element.current)
    chart.setOption(candlestickOption(bars, upColor, downColor))
    const observer = new ResizeObserver(() => chart.resize())
    observer.observe(element.current)
    return () => {
      observer.disconnect()
      chart.dispose()
    }
  }, [bars])

  return (
    <div ref={element} role="img" aria-label="可缩放和拖动的 K 线图" className="h-[420px] w-full" />
  )
}

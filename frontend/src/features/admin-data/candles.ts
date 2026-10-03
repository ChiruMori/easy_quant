import Decimal from "decimal.js"

import type { DailyBar } from "./types"

export type CandlePeriod = "day" | "week" | "month"
export type CandleBar = Pick<DailyBar, "trading_day" | "open" | "high" | "low" | "close">

function periodKey(day: string, period: CandlePeriod): string {
  if (period === "day") return day
  if (period === "month") return day.slice(0, 7)
  const date = new Date(`${day}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() - ((date.getUTCDay() + 6) % 7))
  return date.toISOString().slice(0, 10)
}

export function aggregateCandles(bars: DailyBar[], period: CandlePeriod): CandleBar[] {
  const result: CandleBar[] = []
  let currentKey = ""
  for (const bar of [...bars].sort((left, right) =>
    left.trading_day.localeCompare(right.trading_day),
  )) {
    const key = periodKey(bar.trading_day, period)
    const last = result.at(-1)
    if (key !== currentKey || !last) {
      result.push({
        trading_day: bar.trading_day,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
      })
      currentKey = key
      continue
    }
    last.trading_day = bar.trading_day
    last.high = Decimal.max(last.high, bar.high).toString()
    last.low = Decimal.min(last.low, bar.low).toString()
    last.close = bar.close
  }
  return result
}

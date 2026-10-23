import Decimal from "decimal.js"

export function formatMoney(value?: string | null): string {
  if (value === null || value === undefined || value === "") return "—"
  const number = new Decimal(value)
  return number.isFinite() ? number.toFixed(2) : "—"
}

export function profitTone(value?: string | number | null): "neutral" | "up" | "down" {
  if (value === null || value === undefined || value === "") return "neutral"
  const number = new Decimal(value)
  return number.gt(0) ? "up" : number.lt(0) ? "down" : "neutral"
}

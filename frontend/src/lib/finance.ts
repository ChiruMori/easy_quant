import Decimal from "decimal.js"

export function formatMoney(value?: string | null): string {
  if (value === null || value === undefined || value === "") return "—"
  const number = new Decimal(value)
  return number.isFinite() ? number.toFixed(2) : "—"
}

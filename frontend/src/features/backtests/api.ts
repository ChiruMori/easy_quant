import { apiRequest } from "@/lib/api/client"

export interface Backtest {
  id: string
  strategy_version_id: string
  status: string
  progress: number
  snapshot_id: string
  application_version: string
  metrics: Record<string, string | number | null>
  periods: Array<{ trading_day: string; equity: string; cash?: string }>
  trades: Array<{
    trading_day: string
    symbol: string
    action: string
    quantity: string
    price: string
    fee: string
    slippage?: string
  }>
  assumptions: Record<string, string>
}

export const createBacktest = (payload: Record<string, unknown>) =>
  apiRequest<Backtest>("/backtests", { method: "POST", body: JSON.stringify(payload) })
export const getBacktest = (id: string) => apiRequest<Backtest>(`/backtests/${id}`)
export const listBacktests = () => apiRequest<Backtest[]>("/backtests")
export const compareBacktests = (runIds: [string, string]) =>
  apiRequest<{ runs: Backtest[] }>("/backtests/compare", {
    method: "POST",
    body: JSON.stringify({ run_ids: runIds }),
  })

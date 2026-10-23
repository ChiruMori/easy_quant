import type { RunTiming } from "@/components/run-timing"
import type { StrategyContext } from "@/features/strategies/components/strategy-preview"
import { apiRequest } from "@/lib/api/client"

export interface Backtest {
  strategy?: StrategyContext | null
  config?: { initial_cash: string; parameters?: Record<string, unknown> }
  benchmark?: { symbol: string; name: string } | null
  id: string
  name?: string
  created_at?: string
  job_id?: string
  strategy_version_id: string
  status: string
  progress: number
  snapshot_id: string
  application_version: string
  metrics: Record<string, string | number | null>
  periods: Array<{
    trading_day: string
    equity: string
    benchmark_equity?: string | null
    cash?: string
  }>
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
  error?: string
  timing?: RunTiming
  execution?: { stage: string; trading_day?: string; hook?: string; elapsed_seconds?: number }
  error_details?: { action_url?: string; missing_data?: Array<Record<string, string>> }
}

export const createBacktest = (payload: Record<string, unknown>) =>
  apiRequest<Backtest>("/backtests", { method: "POST", body: JSON.stringify(payload) })
export const getBacktest = (id: string) => apiRequest<Backtest>(`/backtests/${id}`)
export const listBacktests = () => apiRequest<Backtest[]>("/backtests")

export interface StockPerformance {
  symbol: string
  quantity: string
  realized_profit: string
  unrealized_profit: string | null
  profit: string | null
  market_value: string | null
  remaining_cost: string
}
export const getStockPerformance = (id: string, page: number) =>
  apiRequest<{ items: StockPerformance[]; total: number; page: number; page_size: number }>(
    `/backtests/${id}/stock-performance?page=${page}&page_size=20`,
  )
export const compareBacktests = (runIds: [string, string]) =>
  apiRequest<{ runs: Backtest[] }>("/backtests/compare", {
    method: "POST",
    body: JSON.stringify({ run_ids: runIds }),
  })

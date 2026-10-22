import type { StrategyContext } from "@/features/strategies/components/strategy-preview"
import { apiRequest } from "@/lib/api/client"

export interface LiveInstance {
  name?: string
  initial_cash?: string
  parameters?: Record<string, unknown>
  initial_positions?: Record<string, string>
  positions?: Record<string, string>
  subscription_ids?: string[]
  notification_channels?: Array<{ id: string; name: string; enabled: boolean }>
  strategy?: StrategyContext | null
  id: string
  backtest_id: string
  strategy_version_id: string
  status: string
  next_decision_at: string
  recommendations?: Recommendation[]
  operations?: OperationPage
  portfolio?: LivePortfolio
}
export interface Recommendation {
  id: string
  action: string
  instrument_id: string
  quantity: string
  ratio?: string | null
  ratio_basis?: string | null
  reason: string
  status: string
  version: number
  suggested_price?: string
  suggested_fee?: string
  decision_at?: string
  operation_type?: string
  actual_quantity?: string | null
  actual_price?: string | null
  actual_fee?: string | null
}
export interface OperationPage {
  items: Recommendation[]
  total: number
  page: number
  page_size: number
}
export interface LivePortfolio {
  cash: string
  available_cash: string
  reserved_cash: string
  reserved_positions: Record<string, string>
  positions: Record<string, string>
  capital_pool: string | null
  profit: string | null
  return_rate: string | null
  valuation_note: string
  missing_symbols: string[]
  curve: Array<{ at: string; profit: string | null; return_rate: string | null }>
}
export const listOperations = (id: string, page: number, search: string) =>
  apiRequest<OperationPage>(
    `/live-instances/${id}/operations?${new URLSearchParams({ page: String(page), search })}`,
  )
export const manualOperation = (
  id: string,
  mode: "preview" | "record",
  values: Record<string, unknown>,
) =>
  apiRequest<{ required_increase: string; capital_pool: string }>(
    `/live-instances/${id}/manual-operations/${mode}`,
    { method: "POST", body: JSON.stringify(values) },
  )
export interface RecommendationActionResult {
  id: string
  kind: "confirm" | "reject" | "correct"
  recommendation_status: string
  version: number
}
export interface LiveConfiguration {
  name: string
  initial_cash: string
  parameters: Record<string, unknown>
  positions: Record<string, string>
  subscription_ids: string[]
  after_market_enabled: boolean
}
export const startLive = (
  backtestId: string,
  strategyVersionId: string,
  configuration: LiveConfiguration,
) =>
  apiRequest<LiveInstance>("/live-instances", {
    method: "POST",
    body: JSON.stringify({
      backtest_id: backtestId,
      strategy_version_id: strategyVersionId,
      ...configuration,
    }),
  })
export const listLive = () => apiRequest<LiveInstance[]>("/live-instances")
export const getLive = (id: string) => apiRequest<LiveInstance>(`/live-instances/${id}`)
export const pauseLive = (id: string) =>
  apiRequest<LiveInstance>(`/live-instances/${id}/pause`, { method: "POST" })
export const terminateLive = (id: string) =>
  apiRequest<LiveInstance>(`/live-instances/${id}/terminate`, { method: "POST" })
export const actOnRecommendation = (
  id: string,
  kind: "confirm" | "reject" | "correct",
  expectedVersion: number,
  values: Record<string, string> = {},
  idempotencyKey: string = crypto.randomUUID(),
) =>
  apiRequest<RecommendationActionResult>(`/recommendations/${id}/${kind}`, {
    method: "POST",
    body: JSON.stringify({
      idempotency_key: idempotencyKey,
      expected_version: expectedVersion,
      ...values,
    }),
  })

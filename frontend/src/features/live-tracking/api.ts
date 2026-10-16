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
}
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

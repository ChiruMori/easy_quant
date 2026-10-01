import { apiRequest } from "@/lib/api/client"

export interface LiveInstance {
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
  reason: string
  status: string
  version: number
  suggested_price?: string
}
export const startLive = (backtestId: string, strategyVersionId: string) =>
  apiRequest<LiveInstance>("/live-instances", {
    method: "POST",
    body: JSON.stringify({ backtest_id: backtestId, strategy_version_id: strategyVersionId }),
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
) =>
  apiRequest(`/recommendations/${id}/${kind}`, {
    method: "POST",
    body: JSON.stringify({
      idempotency_key: crypto.randomUUID(),
      expected_version: expectedVersion,
      ...values,
    }),
  })

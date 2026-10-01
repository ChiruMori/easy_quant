import { apiRequest } from "@/lib/api/client"

import type { Strategy, StrategyRun, StrategyTemplate } from "./types"

export const listStrategies = () => apiRequest<Strategy[]>("/strategies")
export const createStrategy = (payload: {
  name: string
  description: string
  source_code: string
}) => apiRequest<Strategy>("/strategies", { method: "POST", body: JSON.stringify(payload) })
export const addStrategyVersion = (id: string, sourceCode: string) =>
  apiRequest(`/strategies/${id}/versions`, {
    method: "POST",
    body: JSON.stringify({ source_code: sourceCode }),
  })
export const runStrategy = (id: string, parameters: Record<string, unknown>) =>
  apiRequest<StrategyRun>(`/strategies/${id}/run`, {
    method: "POST",
    body: JSON.stringify({ parameters }),
  })
export const listStrategyTemplates = () => apiRequest<StrategyTemplate[]>("/strategies/templates")

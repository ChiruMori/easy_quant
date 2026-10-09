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
export const runStrategy = (
  id: string,
  tradingDay: string,
  parameters: Record<string, unknown>,
  allowMock = false,
) =>
  apiRequest<StrategyRun>(`/strategies/${id}/run`, {
    method: "POST",
    body: JSON.stringify({ trading_day: tradingDay, parameters, allow_mock: allowMock }),
  })
export const listStrategyRuns = (id: string) => apiRequest<StrategyRun[]>(`/strategies/${id}/runs`)
export const listStrategyTemplates = () => apiRequest<StrategyTemplate[]>("/strategies/templates")

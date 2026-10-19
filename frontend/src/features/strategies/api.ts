import { apiRequest } from "@/lib/api/client"

import type {
  Strategy,
  StrategyPage,
  StrategyRun,
  StrategyTemplate,
  WorkspaceStrategy,
} from "./types"

export const listWorkspace = (page = 1, search = "", state = "") =>
  apiRequest<StrategyPage>(
    `/strategies/workspace?${new URLSearchParams({ page: String(page), page_size: "20", search, state })}`,
  )
export const versionPath = (id: string, versionId: string) =>
  `/strategies/${id}/versions/${versionId}`
export const getStrategyVersion = (id: string, versionId: string) =>
  apiRequest<WorkspaceStrategy>(versionPath(id, versionId))
export const saveStrategyDraft = (
  id: string,
  versionId: string,
  payload: { name: string; description: string; source_code: string; expected_revision: number },
) =>
  apiRequest<WorkspaceStrategy>(versionPath(id, versionId), {
    method: "PUT",
    body: JSON.stringify(payload),
  })
export const forkStrategyVersion = (id: string, versionId: string) =>
  apiRequest<WorkspaceStrategy>(`${versionPath(id, versionId)}/fork`, {
    method: "POST",
    body: JSON.stringify({ confirmed: true }),
  })
export const quickTestEditor = (payload: {
  source_code: string
  trading_day: string
  allow_mock: boolean
  strategy_id?: string
  strategy_version_id?: string
}) =>
  apiRequest<StrategyRun>("/strategies/quick-test", {
    method: "POST",
    body: JSON.stringify(payload),
  })
export const getQuickTest = (id: string) => apiRequest<StrategyRun>(`/strategies/quick-tests/${id}`)

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

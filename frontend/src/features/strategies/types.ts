import type { RunTiming } from "@/components/run-timing"

export interface StrategyVersion {
  id: string
  number: number
  source_code: string
  created_at: string
  state?: StrategyState
  name?: string
  description?: string
  revision?: number
}

export type StrategyState = "draft" | "testing" | "live"
export interface WorkspaceStrategy {
  id: string
  version_id: string
  number: number
  name: string
  description: string
  state: StrategyState
  created_at: string
  revision: number
  source_code?: string
  parent_version_id?: string | null
  live_instances: Array<{ id: string; name: string; status: string }>
}
export interface StrategyPage {
  items: WorkspaceStrategy[]
  page: number
  page_size: number
  total: number
}
export interface Strategy {
  id: string
  name: string
  description: string
  current_version_id: string
  versions: StrategyVersion[]
}
export interface StrategyRun {
  timing?: RunTiming
  id: string
  status: string
  strategy_version_id: string
  trading_day: string
  phase_results: Array<{
    phase: string
    status: string
    signals: Array<{ symbol: string; action: string; quantity: string; reason: string }>
    stdout: string
    error?: string
  }>
  error?: string
  allow_mock?: boolean
  mock_usage?: Array<{ factor: string; symbol: string; count: number }>
  portfolio?: { cash: string; positions: Record<string, string> }
}
export interface StrategyTemplate {
  key: string
  name: string
  source_code: string
}

export interface LibraryEntry {
  key: string
  name: string
  signature: string
  description: string
  parameters: string
  output: string
  example: string
  runtime: string
}

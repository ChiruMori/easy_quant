export interface StrategyVersion {
  id: string
  number: number
  source_code: string
  created_at: string
}
export interface Strategy {
  id: string
  name: string
  description: string
  current_version_id: string
  versions: StrategyVersion[]
}
export interface StrategyRun {
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
}
export interface StrategyTemplate {
  key: string
  name: string
  source_code: string
}

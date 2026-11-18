import { apiRequest } from "@/lib/api/client"

export interface FactorDefinition {
  key: string
  name: string
  description: string
  parameters: Record<string, string>
  output: string
  example: string
  output_example: string
  defaults?: Record<string, unknown>
  integer_parameters?: string[]
  calls?: number
  total_ms?: number
  average_ms?: number | null
}

export const listFactors = () => apiRequest<FactorDefinition[]>("/factors")

export const quickTestFactor = (
  key: string,
  trading_day: string,
  parameters: Record<string, unknown>,
) =>
  apiRequest<{ result: unknown; rows: number; elapsed_ms: number; decision_at: string }>(
    `/factors/${encodeURIComponent(key)}/quick-test`,
    { method: "POST", body: JSON.stringify({ trading_day, parameters }) },
  )

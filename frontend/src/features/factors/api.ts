import { apiRequest } from "@/lib/api/client"

export interface FactorDefinition {
  key: string
  name: string
  description: string
  parameters: Record<string, string>
  output: string
  example: string
  output_example: string
}

export const listFactors = () => apiRequest<FactorDefinition[]>("/factors")

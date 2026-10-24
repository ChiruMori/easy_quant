import { useQuery } from "@tanstack/react-query"

import { CodeWorkspace } from "@/components/code-workspace"
import { apiRequest } from "@/lib/api/client"

import type { LibraryEntry } from "../types"

export function StrategyEditor({
  value,
  onChange,
}: {
  value: string
  onChange: (value: string) => void
}) {
  const library = useQuery({
    queryKey: ["strategy-library"],
    queryFn: () => apiRequest<LibraryEntry[]>("/strategy-library"),
  })
  return (
    <CodeWorkspace value={value} onChange={onChange} readOnly={false} completions={library.data} />
  )
}

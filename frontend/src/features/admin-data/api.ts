import { useQuery } from "@tanstack/react-query"

import { apiRequest } from "@/lib/api/client"

import type { Acquisition, Dataset, ImportPreview, MarketDataCoverage } from "./types"

export function useDatasets() {
  return useQuery({
    queryKey: ["admin", "datasets"],
    queryFn: () => apiRequest<Dataset[]>("/admin/market-data/datasets"),
  })
}

export function useMarketDataCoverage() {
  return useQuery({
    queryKey: ["admin", "market-data", "coverage"],
    queryFn: () => apiRequest<MarketDataCoverage>("/admin/market-data/coverage"),
  })
}

export function startAcquisition(
  datasetKey: string,
  force = false,
  range?: { symbols?: string[]; start_day?: string; end_day?: string },
) {
  return apiRequest<Acquisition>("/admin/market-data/acquisitions", {
    method: "POST",
    body: JSON.stringify({ dataset_key: datasetKey, force, ...range }),
  })
}

export function updateDatasetSources(
  datasetKey: string,
  sourceKeys: string[],
  enabledKeys: string[],
) {
  return apiRequest<Dataset>(`/admin/market-data/datasets/${datasetKey}/sources`, {
    method: "PUT",
    body: JSON.stringify({ source_keys: sourceKeys, enabled_keys: enabledKeys }),
  })
}

export function previewImport(file: File, datasetKey = "daily-bars") {
  const body = new FormData()
  body.set("file", file)
  body.set("dataset_key", datasetKey)
  return apiRequest<ImportPreview>("/admin/market-data/imports/preview", { method: "POST", body })
}

export function commitImport(previewId: string) {
  return apiRequest<{ status: string; rows: number; overwritten: number }>(
    "/admin/market-data/imports/commit",
    {
      method: "POST",
      body: JSON.stringify({ preview_id: previewId }),
    },
  )
}

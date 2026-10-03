import { useQuery } from "@tanstack/react-query"

import { apiRequest } from "@/lib/api/client"

import type {
  Acquisition,
  DailyBar,
  Dataset,
  ImportPreview,
  Instrument,
  MarketDataCoverage,
} from "./types"

export function useDatasets() {
  return useQuery({
    queryKey: ["admin", "datasets"],
    queryFn: () => apiRequest<Dataset[]>("/admin/market-data/datasets"),
  })
}

export function useMarketDataCoverage(params: {
  page: number
  search?: string
  status?: string
  after?: string
  before?: string
}) {
  const query = new URLSearchParams({ page: String(params.page), page_size: "50" })
  if (params.search) query.set("search", params.search)
  if (params.status) query.set("status", params.status)
  if (params.after) query.set("after", params.after)
  if (params.before) query.set("before", params.before)
  return useQuery({
    queryKey: ["admin", "market-data", "coverage", params],
    queryFn: () =>
      apiRequest<MarketDataCoverage>(`/admin/market-data/coverage?${query.toString()}`),
  })
}

export const getAcquisition = (id: string) =>
  apiRequest<Acquisition>(`/admin/market-data/acquisitions/${id}`)

export const getInstrument = (symbol: string) =>
  apiRequest<Instrument>(`/admin/market-data/instruments/${symbol}`)

export const getInstrumentDailyBars = (symbol: string, startDay?: string, endDay?: string) => {
  const query = new URLSearchParams()
  if (startDay) query.set("start_day", startDay)
  if (endDay) query.set("end_day", endDay)
  return apiRequest<DailyBar[]>(
    `/admin/market-data/instruments/${symbol}/daily-bars?${query.toString()}`,
  )
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

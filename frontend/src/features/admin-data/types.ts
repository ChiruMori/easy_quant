export interface Dataset {
  key: string
  name: string
  description: string
  sources: Array<{ key: string; name: string; enabled: boolean }>
}

export interface Acquisition {
  id: string
  dataset_key: string
  force: boolean
  status: string
  source?: string
  record_count?: number
  message?: string
  attempts?: Array<{ source_key: string; attempt: number; status: string; message?: string }>
}

export interface ImportPreview {
  preview_id: string | null
  valid: boolean
  rows: number
  issues: Array<{ row: number; field: string; message: string }>
}

export interface MarketDataCoverage {
  instrument_count: number
  items: Array<{
    symbol: string
    name: string
    exchange: string
    listed_on: string | null
    first_trading_day: string | null
    last_trading_day: string | null
    record_count: number
    sync_status: "完全同步" | "部分同步" | "数据不足" | "未同步"
    freshness_status: "updated" | "stale" | "not_updated"
    updated: boolean
    stale: boolean
    previous_trading_day: string
    recommended_end_day: string
  }>
}

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

vi.mock("./api", () => ({
  useDatasets: () => ({
    isLoading: false,
    data: [
      {
        key: "bars",
        name: "日线 K 线",
        description: "每日行情",
        sources: [
          { key: "akshare", name: "AKShare", enabled: true },
          { key: "eastmoney", name: "东方财富", enabled: true },
        ],
      },
    ],
  }),
  useMarketDataCoverage: () => ({
    isLoading: false,
    data: {
      instrument_count: 1,
      items: [
        {
          symbol: "000001",
          name: "平安银行",
          exchange: "深圳证券交易所",
          first_trading_day: "2015-01-05",
          last_trading_day: "2026-09-30",
          record_count: 2800,
          sync_status: "完全同步",
          freshness_status: "updated",
          updated: true,
          stale: false,
          previous_trading_day: "2026-09-30",
          recommended_end_day: "2026-10-01",
        },
      ],
    },
  }),
}))
import { DatasetsPage } from "./pages/datasets-page"

describe("数据管理主旅程", () => {
  it("展示数据集及股票数据覆盖", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <DatasetsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(screen.getByText("日线 K 线")).toBeInTheDocument()
    expect(screen.getByText(/已配置 2 个可用来源/)).toBeInTheDocument()
    expect(screen.getByText(/000001 平安银行/)).toBeInTheDocument()
    expect(screen.getAllByText("完全同步").length).toBeGreaterThan(0)
    expect(screen.getByText("已更新")).toBeInTheDocument()
  })
})

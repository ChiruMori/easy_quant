import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

const coverageSpy = vi.hoisted(() => vi.fn())

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
  useMarketDataCoverage: (params: unknown) => {
    coverageSpy(params)
    return {
      isLoading: false,
      data: {
        instrument_count: 1,
        total: 6001,
        page: 1,
        page_size: 50,
        next_cursor: "000001",
        previous_cursor: "000001",
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
    }
  },
}))
import { DatasetsPage } from "./pages/datasets-page"

afterEach(cleanup)

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

  it("支持页码跳转，上一页和下一页使用代码游标", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <DatasetsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    fireEvent.change(screen.getByLabelText("页码"), { target: { value: "120" } })
    fireEvent.click(screen.getByRole("button", { name: "跳转" }))
    expect(coverageSpy).toHaveBeenLastCalledWith(expect.objectContaining({ page: 120 }))
    fireEvent.click(screen.getByRole("button", { name: "下一页" }))
    expect(coverageSpy).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 121, after: "000001" }),
    )
  })
})

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

const controls = vi.hoisted(() => ({
  coverageSpy: vi.fn(),
  showStale: false,
  startAcquisition: vi.fn(),
  getAcquisition: vi.fn(),
}))

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
    controls.coverageSpy(params)
    return {
      isLoading: false,
      data: {
        instrument_count: 2,
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
            status: "active",
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
          {
            symbol: "000002",
            name: "退市股票",
            exchange: "深圳证券交易所",
            status: "delisted",
            first_trading_day: "2015-01-05",
            last_trading_day: "2020-01-02",
            record_count: 1000,
            sync_status: "已退市",
            freshness_status: "delisted",
            updated: false,
            stale: false,
            previous_trading_day: "2026-09-30",
            recommended_end_day: "2026-10-01",
          },
          ...(controls.showStale
            ? [
                {
                  symbol: "000016",
                  name: "*ST康佳A",
                  exchange: "深圳证券交易所",
                  status: "active",
                  first_trading_day: "1992-03-27",
                  last_trading_day: "2026-09-03",
                  record_count: 8191,
                  sync_status: "完全同步",
                  freshness_status: "stale",
                  updated: false,
                  stale: true,
                  previous_trading_day: "2026-09-30",
                  recommended_end_day: "2026-09-30",
                },
              ]
            : []),
        ],
      },
    }
  },
  startAcquisition: controls.startAcquisition,
  getAcquisition: controls.getAcquisition,
}))
import { DatasetsPage } from "./pages/datasets-page"

afterEach(() => {
  cleanup()
  controls.showStale = false
  controls.startAcquisition.mockReset()
  controls.getAcquisition.mockReset()
})

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
    expect(screen.getAllByText("已退市").length).toBeGreaterThan(0)
    expect(screen.queryByText("已过时")).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /更新至/ })).not.toBeInTheDocument()
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
    expect(controls.coverageSpy).toHaveBeenLastCalledWith(expect.objectContaining({ page: 120 }))
    fireEvent.click(screen.getByRole("button", { name: "下一页" }))
    expect(controls.coverageSpy).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 121, after: "000001" }),
    )
  })

  it("点击更新后持续显示任务结果和来源失败原因", async () => {
    controls.showStale = true
    controls.startAcquisition.mockResolvedValue({
      id: "task-1",
      symbols: ["000016"],
      status: "queued",
    })
    controls.getAcquisition.mockResolvedValue({
      id: "task-1",
      symbols: ["000016"],
      status: "failed",
      message: "所有数据来源均失败",
      attempts: [{ source_key: "eastmoney", attempt: 1, status: "failed", message: "连接已断开" }],
    })
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <DatasetsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    fireEvent.click(screen.getByRole("button", { name: "更新至 2026-09-30" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("所有数据来源均失败")
    fireEvent.click(screen.getByText("查看来源失败原因"))
    expect(screen.getByText(/eastmoney 第 1 次：连接已断开/)).toBeInTheDocument()
  })
})

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

const controls = vi.hoisted(() => ({
  coverageSpy: vi.fn(),
  showStale: false,
  suspended: false,
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
        recommended_end_day: "2026-10-14",
        calendar_estimated: true,
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
                  status: controls.suspended ? "suspended" : "active",
                  first_trading_day: "1992-03-27",
                  last_trading_day: "2026-09-03",
                  record_count: 8191,
                  sync_status: "数据落后",
                  freshness_status: "stale",
                  updated: false,
                  stale: true,
                  publication_pending: controls.suspended,
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
  controls.suspended = false
  controls.startAcquisition.mockReset()
  controls.getAcquisition.mockReset()
})

describe("数据管理主旅程", () => {
  it("数据落后与已过时同义时只显示一个状态标签", () => {
    controls.showStale = true
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <DatasetsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    const row = screen.getByRole("row", { name: /000016/ })
    expect(within(row).getByText("数据落后")).toBeInTheDocument()
    expect(within(row).queryByText("已过时")).not.toBeInTheDocument()
  })
  it("停牌覆盖优先，隐藏落后、发布等待和日线同步入口", () => {
    controls.showStale = true
    controls.suspended = true
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <DatasetsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    const row = screen.getByText(/000016/).closest("tr")!
    expect(within(row).getByText("已停牌")).toBeInTheDocument()
    expect(within(row).queryByText("数据落后")).not.toBeInTheDocument()
    expect(within(row).queryByText("已过时")).not.toBeInTheDocument()
    expect(within(row).queryByText("来源尚未发布新数据")).not.toBeInTheDocument()
    expect(within(row).queryByRole("button")).not.toBeInTheDocument()
  })

  it("批量刷新停复牌状态并显示异步结果", async () => {
    controls.startAcquisition.mockResolvedValue({
      id: "status-1",
      dataset_key: "trading-status",
      status: "queued",
    })
    controls.getAcquisition.mockResolvedValue({
      id: "status-1",
      dataset_key: "trading-status",
      status: "succeeded",
      record_count: 4,
      message: "已确认 4 只股票整日停牌",
    })
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <DatasetsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    fireEvent.keyDown(screen.getByRole("button", { name: "数据维护" }), { key: "ArrowDown" })
    fireEvent.click(await screen.findByRole("menuitem", { name: "刷新停复牌状态" }))
    expect(controls.startAcquisition).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole("button", { name: "取消" }))
    expect(controls.startAcquisition).not.toHaveBeenCalled()
    fireEvent.keyDown(screen.getByRole("button", { name: "数据维护" }), { key: "ArrowDown" })
    fireEvent.click(await screen.findByRole("menuitem", { name: "刷新停复牌状态" }))
    fireEvent.click(screen.getByRole("button", { name: "确认刷新停复牌状态" }))
    expect(controls.startAcquisition).toHaveBeenCalledWith("trading-status", true, {
      end_day: "2026-10-14",
    })
    expect(await screen.findByText(/已确认 4 只股票整日停牌/)).toBeInTheDocument()
  })
  it("展示数据集及股票数据覆盖", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <DatasetsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(screen.getByText("日线 K 线")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "数据维护" })).toBeInTheDocument()
    expect(screen.getByRole("tab", { name: "股票" })).toHaveAttribute("aria-selected", "true")
    expect(screen.getByRole("tab", { name: "指数" })).toBeInTheDocument()
    expect(screen.getByText(/当前应更新至 2026-10-14/)).toBeInTheDocument()
    expect(screen.getByText(/当前按工作日估算/)).toBeInTheDocument()
    expect(controls.startAcquisition).not.toHaveBeenCalled()
    expect(screen.getByRole("button", { name: "AKShare 已启用" })).toHaveAttribute(
      "aria-pressed",
      "true",
    )
    expect(screen.queryByRole("button", { name: "保存来源配置" })).not.toBeInTheDocument()
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

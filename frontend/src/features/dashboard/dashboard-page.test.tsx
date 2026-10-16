import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { type Backtest, listBacktests } from "@/features/backtests/api"
import { BacktestTable } from "@/features/backtests/components/backtest-table"
import { listLive } from "@/features/live-tracking/api"
import { listStrategies } from "@/features/strategies/api"

import { DashboardPage } from "./dashboard-page"

vi.mock("@/features/backtests/api", () => ({ listBacktests: vi.fn() }))
vi.mock("@/features/live-tracking/api", () => ({ listLive: vi.fn() }))
vi.mock("@/features/strategies/api", () => ({ listStrategies: vi.fn() }))

const run: Backtest = {
  id: "run-1",
  strategy_version_id: "version-1",
  status: "succeeded",
  progress: 100,
  snapshot_id: "snapshot-1",
  application_version: "test-v1",
  metrics: { cumulative_return: "0.1842" },
  periods: [],
  trades: [],
  assumptions: {},
}

function renderDashboard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(cleanup)
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(listStrategies).mockResolvedValue([])
  vi.mocked(listBacktests).mockResolvedValue([])
  vi.mocked(listLive).mockResolvedValue([])
})

describe("研究概览", () => {
  it("按真实列表统计状态，不合并不同策略的收益", async () => {
    vi.mocked(listBacktests).mockResolvedValue([
      run,
      { ...run, id: "run-2", status: "failed", metrics: {} },
    ])
    vi.mocked(listLive).mockResolvedValue(
      ["active", "paused", "terminated"].map((status) => ({
        id: status,
        status,
        backtest_id: "run-1",
        strategy_version_id: "version-1",
        next_decision_at: "2026-10-15T01:00:00Z",
      })),
    )
    renderDashboard()
    await screen.findByRole("heading", { name: "研究概览" })
    expect(
      within(screen.getByRole("region", { name: "回测记录" })).getByText("2"),
    ).toBeInTheDocument()
    expect(
      within(screen.getByRole("region", { name: "运行中的实盘" })).getByText("1"),
    ).toBeInTheDocument()
    expect(screen.getByText("18.42%")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "run-1" })).toHaveAttribute("href", "/backtests/run-1")
  })
  it("加载时不显示误导性的零值统计", () => {
    vi.mocked(listBacktests).mockReturnValue(new Promise(() => undefined))
    renderDashboard()
    expect(screen.getByLabelText("正在加载工作台概览")).toBeInTheDocument()
    expect(screen.queryByRole("region", { name: "回测记录" })).not.toBeInTheDocument()
  })
  it("读取失败显示错误，重试成功后展示真实空态", async () => {
    vi.mocked(listBacktests).mockRejectedValueOnce(new Error("回测暂不可用"))
    renderDashboard()
    expect(await screen.findByText("回测暂不可用")).toBeInTheDocument()
    expect(screen.queryByRole("region", { name: "回测记录" })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "重新加载" }))
    expect(await screen.findByText("尚无回测记录")).toBeInTheDocument()
    expect(
      within(screen.getByRole("region", { name: "回测记录" })).getByText("0"),
    ).toBeInTheDocument()
  })
  it("排队记录中文呈现，缺失指标不显示 NaN 或零收益", () => {
    render(
      <MemoryRouter>
        <BacktestTable runs={[{ ...run, status: "queued", metrics: {} }]} />
      </MemoryRouter>,
    )
    expect(screen.getByText("排队中")).toBeInTheDocument()
    expect(screen.getAllByText("—")).toHaveLength(3)
    expect(screen.queryByText("NaN")).not.toBeInTheDocument()
  })
})

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

import { BacktestDetailPage } from "./pages/backtest-detail-page"

vi.mock("./api", () => ({
  getStockPerformance: async () => ({ items: [], total: 0, page: 1, page_size: 20 }),
}))

describe("回测详情", () => {
  it("展示指标、交易、假设和追溯身份", () => {
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <MemoryRouter>
          <BacktestDetailPage
            run={{
              id: "b1",
              strategy_version_id: "v1",
              status: "succeeded",
              progress: 100,
              snapshot_id: "s1",
              application_version: "0.1",
              metrics: { cumulative_return: "0.1" },
              periods: [],
              trades: [],
              assumptions: { frequency: "daily" },
              timing: {
                total_seconds: 2,
                workload: {},
                stages: { warmup: 0.5, strategy: 1.5 },
                hooks: {
                  before_market: { count: 1, total_seconds: 1, average_seconds: 1, max_seconds: 1 },
                },
                daily_hooks: [{ trading_day: "2026-10-09", hook: "before_market", seconds: 1 }],
              },
            }}
          />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(screen.getByText("交易与假设披露")).toBeInTheDocument()
    expect(screen.getByText("累计收益率")).toBeInTheDocument()
    expect(screen.getByText("10%")).toBeInTheDocument()
    expect(screen.getByText(/快照 s1/)).toBeInTheDocument()
    expect(screen.getByText("运行耗时")).toBeInTheDocument()
    expect(screen.getByText("平均耗时（秒）")).toBeInTheDocument()
    expect(screen.getByText("2026-10-09")).toBeInTheDocument()
  })
})

import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"

import { BacktestDetailPage } from "./pages/backtest-detail-page"

describe("回测详情", () => {
  it("展示指标、交易、假设和追溯身份", () => {
    render(
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
          }}
        />
      </MemoryRouter>,
    )
    expect(screen.getByText("交易与假设披露")).toBeInTheDocument()
    expect(screen.getByText("累计收益率")).toBeInTheDocument()
    expect(screen.getByText("10%")).toBeInTheDocument()
    expect(screen.getByText(/快照 s1/)).toBeInTheDocument()
  })
})

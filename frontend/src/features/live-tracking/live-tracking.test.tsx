import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"

import { LiveListPage } from "./pages/live-list-page"

describe("实盘跟踪", () => {
  it("明确仅提供建议且展示实例", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <LiveListPage
            instances={[
              {
                id: "l1",
                backtest_id: "b1",
                strategy_version_id: "v1",
                status: "active",
                next_decision_at: "2026-10-01",
              },
            ]}
          />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(screen.getByText(/不会自动下单/)).toBeInTheDocument()
    expect(screen.getByText(/l1/)).toBeInTheDocument()
  })
})

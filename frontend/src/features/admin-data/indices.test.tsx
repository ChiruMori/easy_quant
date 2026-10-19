import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { getAcquisition, listIndices, syncIndices } from "./api"
import { IndicesPanel } from "./pages/indices-page"

vi.mock("./api", () => ({ listIndices: vi.fn(), syncIndices: vi.fn(), getAcquisition: vi.fn() }))
const data = {
  recommended_end_day: "2026-09-29",
  calendar_estimated: false,
  items: [
    {
      symbol: "sh000300",
      name: "沪深300",
      exchange: "上海证券交易所",
      tradable: false as const,
      adjustment: "none" as const,
      first_trading_day: null,
      last_trading_day: null,
      record_count: 0,
      sync_status: "未同步",
    },
  ],
}
const renderPage = () =>
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <IndicesPanel />
      </MemoryRouter>
    </QueryClientProvider>,
  )
afterEach(cleanup)
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(listIndices).mockResolvedValue(data)
})

describe("指数数据", () => {
  it("未同步时显示目录，阻止空选择并按独立区间提交任务", async () => {
    vi.mocked(syncIndices).mockResolvedValue({
      id: "index-task",
      status: "queued",
      dataset_key: "daily-bars",
      force: true,
    })
    vi.mocked(getAcquisition).mockResolvedValue({
      id: "index-task",
      dataset_key: "daily-bars",
      force: true,
      status: "succeeded",
      record_count: 2,
    })
    renderPage()
    await screen.findByText("沪深300")
    expect(screen.getByText("未同步")).toBeInTheDocument()
    expect(screen.getByRole("checkbox", { name: "选择沪深300" })).not.toBeChecked()
    fireEvent.click(screen.getByRole("button", { name: "同步所选指数" }))
    expect(screen.getByText("请至少选择一个指数")).toBeInTheDocument()
    expect(syncIndices).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole("button", { name: "全选主要指数" }))
    fireEvent.change(screen.getByLabelText("指数开始日期"), { target: { value: "2026-09-28" } })
    fireEvent.click(screen.getByRole("button", { name: "同步所选指数" }))
    await waitFor(() =>
      expect(syncIndices).toHaveBeenCalledWith({
        symbols: ["sh000300"],
        start_day: "2026-09-28",
        end_day: "2026-09-29",
      }),
    )
    await screen.findByText("指数同步任务：已成功")
  })
  it("目录请求失败不能伪装为零覆盖", async () => {
    vi.mocked(listIndices).mockRejectedValue(new Error("目录不可用"))
    renderPage()
    await screen.findByText("目录不可用")
    expect(screen.queryByText("主要指数")).not.toBeInTheDocument()
  })
  it("同步失败展示错误，允许修正后重试", async () => {
    vi.mocked(syncIndices).mockRejectedValue(new Error("来源配置不可用"))
    renderPage()
    await screen.findByText("沪深300")
    fireEvent.click(screen.getByRole("checkbox", { name: "选择沪深300" }))
    fireEvent.click(screen.getByRole("button", { name: "同步所选指数" }))
    await screen.findByText("来源配置不可用")
    expect(screen.getByRole("button", { name: "同步所选指数" })).toBeEnabled()
  })
})

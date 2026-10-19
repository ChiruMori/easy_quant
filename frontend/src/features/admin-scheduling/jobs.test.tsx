import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"

import { listJobs } from "./api"
import { JobsPage } from "./pages/jobs-page"

vi.mock("./api", () => ({ listJobs: vi.fn() }))
afterEach(() => {
  cleanup()
  vi.resetAllMocks()
})

const renderPage = () =>
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <JobsPage />
    </QueryClientProvider>,
  )

it("后台任务向服务端翻页、跳页并展示总数", async () => {
  vi.mocked(listJobs).mockImplementation(async (page = 1) => ({
    items: [
      {
        id: `job-${page}`,
        job_type: `任务第${page}页`,
        status: "succeeded",
        available_at: "2026-09-29T08:00:00Z",
        attempt_count: 1,
      },
    ],
    total: 45,
    page,
    page_size: 20,
  }))
  renderPage()
  await screen.findByText("任务第1页")
  expect(screen.getByRole("button", { name: "上一页" })).toBeDisabled()
  fireEvent.click(screen.getByRole("button", { name: "下一页" }))
  await screen.findByText("任务第2页")
  expect(listJobs).toHaveBeenLastCalledWith(2)
  fireEvent.change(screen.getByRole("spinbutton", { name: "跳转页码" }), { target: { value: "3" } })
  fireEvent.click(screen.getByRole("button", { name: /^跳转$/ }))
  await screen.findByText("任务第3页")
  expect(screen.getByRole("button", { name: "下一页" })).toBeDisabled()
  expect(screen.getByText(/共 45 个任务 · 第 3 \/ 3 页/)).toBeInTheDocument()
})

it("加载失败显示错误并可重试，空列表不显示分页", async () => {
  vi.mocked(listJobs)
    .mockRejectedValueOnce(new Error("任务不可用"))
    .mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
  renderPage()
  await screen.findByText("任务不可用")
  fireEvent.click(screen.getByRole("button", { name: "重试" }))
  await screen.findByText("暂无后台任务")
  expect(screen.queryByRole("navigation", { name: "后台任务分页" })).not.toBeInTheDocument()
})

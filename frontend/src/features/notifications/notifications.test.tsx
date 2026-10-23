import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, expect, it, vi } from "vitest"

const api = vi.hoisted(() => ({
  listSubscriptionsPage: vi.fn(),
  listDeliveries: vi.fn(),
  getSubscription: vi.fn(),
  updateSubscription: vi.fn(),
  addSubscription: vi.fn(),
  testSubscription: vi.fn(),
}))
vi.mock("./api", () => api)
import { NotificationSettingsPage } from "./pages/notification-settings-page"

const item = {
  id: "disabled",
  name: "停用提醒",
  channel: "ntfy",
  destination: "***",
  enabled: false,
}
function mount() {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <NotificationSettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}
beforeEach(() => {
  vi.clearAllMocks()
  api.listSubscriptionsPage.mockImplementation(async (page) => ({
    items: [{ ...item, name: page === 1 ? item.name : "第二页渠道" }],
    page,
    page_size: 10,
    total: 11,
  }))
  api.listDeliveries.mockImplementation(async (page) => ({
    items: [
      {
        id: `d${page}`,
        channel: "ntfy",
        status: page === 1 ? "delivered" : "retry",
        attempts: page,
        error_code: page === 2 ? "ntfy_transport" : undefined,
      },
    ],
    page,
    page_size: 10,
    total: 11,
  }))
  api.getSubscription.mockResolvedValue({ ...item, destination: "fixture-topic" })
})
afterEach(cleanup)

it("停用渠道仍可编辑、显隐和失败重试，保存不启用", async () => {
  mount()
  await screen.findByRole("button", { name: "编辑渠道 停用提醒" }, { timeout: 5000 })
  expect(api.getSubscription).not.toHaveBeenCalled()
  expect(screen.queryByText("fixture-topic")).not.toBeInTheDocument()
  expect(screen.queryByRole("button", { name: /测试连通性/ })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "编辑渠道 停用提醒" }))
  await waitFor(() => expect(screen.getByLabelText("通知目标")).toHaveValue("fixture-topic"))
  expect(screen.getByLabelText("通知目标")).toHaveAttribute("type", "password")
  fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "显示通知目标" }))
  expect(screen.getByLabelText("通知目标")).toHaveAttribute("type", "text")
  fireEvent.change(screen.getByLabelText("通知目标"), { target: { value: "edited-fixture" } })
  api.updateSubscription.mockRejectedValueOnce(new Error("保存失败"))
  fireEvent.click(screen.getByRole("button", { name: "保存渠道" }))
  expect(await screen.findByRole("alert")).toHaveTextContent("保存失败")
  expect(screen.getByLabelText("通知目标")).toHaveValue("edited-fixture")
  api.updateSubscription.mockResolvedValue(item)
  fireEvent.click(screen.getByRole("button", { name: "保存渠道" }))
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
  expect(api.updateSubscription).toHaveBeenLastCalledWith(
    "disabled",
    false,
    "停用提醒",
    "edited-fixture",
  )
})

it("渠道和投递独立分页，目标按需显示再隐藏，读取失败可重试", async () => {
  api.listDeliveries.mockRejectedValueOnce(new Error("列表暂不可用"))
  mount()
  expect(await screen.findByRole("alert")).toHaveTextContent("列表暂不可用")
  fireEvent.click(screen.getByRole("button", { name: "重试投递列表" }))
  await screen.findByText("渠道已接收")
  fireEvent.click(screen.getByRole("button", { name: "显示通知目标 停用提醒" }))
  await screen.findByText("fixture-topic")
  fireEvent.click(screen.getByRole("button", { name: "隐藏通知目标 停用提醒" }))
  await waitFor(() => expect(screen.queryByText("fixture-topic")).not.toBeInTheDocument())
  fireEvent.click(
    within(screen.getByRole("navigation", { name: "通知渠道分页" })).getByRole("button", {
      name: "下一页",
    }),
  )
  await screen.findByRole("button", { name: "编辑渠道 第二页渠道" })
  expect(api.listSubscriptionsPage).toHaveBeenLastCalledWith(2)
  fireEvent.click(
    within(screen.getByRole("navigation", { name: "投递记录分页" })).getByRole("button", {
      name: "下一页",
    }),
  )
  expect(await screen.findByText(/ntfy_transport/)).toBeInTheDocument()
  expect(api.listDeliveries).toHaveBeenLastCalledWith(2)
})

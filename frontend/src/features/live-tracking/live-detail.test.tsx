import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import type { PropsWithChildren } from "react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  actOnRecommendation,
  getLive,
  getLiveDeliveries,
  getLivePortfolio,
  listOperations,
  pauseLive,
} from "./api"
import { LiveDetailPage } from "./pages/live-detail-page"

vi.mock("./api", () => ({
  actOnRecommendation: vi.fn(),
  getLive: vi.fn(),
  getLivePortfolio: vi.fn(),
  getLiveDeliveries: vi.fn(),
  pauseLive: vi.fn(),
  terminateLive: vi.fn(),
  resumeLive: vi.fn(),
  listOperations: vi.fn(),
  manualOperation: vi.fn(),
}))

const instance = {
  id: "live",
  backtest_id: "b",
  strategy_version_id: "v",
  status: "active",
  next_decision_at: "",
  recommendations: [
    {
      id: "r",
      action: "buy",
      instrument_id: "000001",
      quantity: "10",
      reason: "测试建议",
      status: "pending",
      version: 0,
    },
  ],
}
const result = {
  id: "operation",
  kind: "confirm" as const,
  recommendation_status: "confirmed",
  version: 1,
}

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(cleanup)

describe("实盘建议处理反馈", () => {
  it("其他页面已处理建议时，冲突后刷新列表并禁用重复操作", async () => {
    const operations = {
      items: instance.recommendations.map((row) => ({ ...row, status: "confirmed", version: 1 })),
      page: 1,
      page_size: 20,
      total: 1,
    }
    vi.mocked(actOnRecommendation).mockRejectedValueOnce(new Error("建议已被其他请求处理"))
    vi.mocked(getLive).mockResolvedValue({ ...instance, operations })
    vi.mocked(listOperations).mockResolvedValue(operations)
    render(
      <TestRouter>
        <LiveDetailPage instance={instance} />
      </TestRouter>,
    )
    fireEvent.click(screen.getByRole("button", { name: "接受建议" }))
    fireEvent.click(screen.getByRole("button", { name: "确认接受建议" }))
    await screen.findAllByText("建议已被其他请求处理")
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument())
    expect(screen.queryByRole("button", { name: "接受建议" })).not.toBeInTheDocument()
    expect(listOperations).toHaveBeenCalledWith("live", 1, "", "", "")
  })
  it("成功后立即更新状态并禁用已处理按钮", async () => {
    vi.mocked(actOnRecommendation).mockResolvedValue(result)
    render(
      <TestRouter>
        <LiveDetailPage instance={instance} />
      </TestRouter>,
    )
    fireEvent.click(screen.getByRole("button", { name: "接受建议" }))
    fireEvent.click(screen.getByRole("button", { name: "确认接受建议" }))
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument())
    expect(screen.queryByRole("button", { name: "接受建议" })).not.toBeInTheDocument()
    expect(await screen.findByRole("cell", { name: "已操作" })).toBeInTheDocument()
    expect(actOnRecommendation).toHaveBeenCalledTimes(1)
  })
  it("显示失败原因，相同请求重试保持幂等键", async () => {
    vi.mocked(actOnRecommendation)
      .mockRejectedValueOnce(new Error("账本产生负现金"))
      .mockResolvedValueOnce(result)
    vi.mocked(getLive).mockResolvedValue(instance)
    render(
      <TestRouter>
        <LiveDetailPage instance={instance} />
      </TestRouter>,
    )
    fireEvent.click(screen.getByRole("button", { name: "接受建议" }))
    fireEvent.click(screen.getByRole("button", { name: "确认接受建议" }))
    await screen.findAllByText("账本产生负现金")
    await waitFor(() => expect(screen.getByRole("button", { name: "确认接受建议" })).toBeEnabled())
    fireEvent.click(screen.getByRole("button", { name: "确认接受建议" }))
    await waitFor(() => expect(actOnRecommendation).toHaveBeenCalledTimes(2))
    expect(vi.mocked(actOnRecommendation).mock.calls[0][4]).toBe(
      vi.mocked(actOnRecommendation).mock.calls[1][4],
    )
  })
  it("处理中阻止重复点击", async () => {
    let resolve!: (value: typeof result) => void
    vi.mocked(actOnRecommendation).mockReturnValue(
      new Promise((done) => {
        resolve = done
      }),
    )
    render(
      <TestRouter>
        <LiveDetailPage instance={instance} />
      </TestRouter>,
    )
    const button = screen.getByRole("button", { name: "接受建议" })
    fireEvent.click(button)
    const confirm = screen.getByRole("button", { name: "确认接受建议" })
    fireEvent.click(confirm)
    fireEvent.click(confirm)
    expect(actOnRecommendation).toHaveBeenCalledTimes(1)
    expect(screen.getByRole("status")).toHaveTextContent("正在处理")
    resolve(result)
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument())
  })
  it("暂停更新不丢失已加载建议", async () => {
    vi.mocked(pauseLive).mockResolvedValue({
      id: instance.id,
      backtest_id: instance.backtest_id,
      strategy_version_id: instance.strategy_version_id,
      status: "paused",
      next_decision_at: instance.next_decision_at,
    })
    render(
      <TestRouter>
        <LiveDetailPage instance={instance} />
      </TestRouter>,
    )
    fireEvent.click(screen.getByRole("button", { name: "暂停" }))
    expect(pauseLive).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole("button", { name: "确认暂停" }))
    await screen.findByText("状态：已暂停")
    expect(screen.getByText(/测试建议/)).toBeInTheDocument()
  })
})

it("显示实盘名称、独立资金和历史策略代码及链接", async () => {
  render(
    <TestRouter>
      <LiveDetailPage
        instance={{
          ...instance,
          name: "我的实盘",
          initial_cash: "2000.25",
          parameters: { quantity: 5 },
          notification_channels: [{ id: "n", name: "个人推送", enabled: true }],
          strategy: {
            id: "s",
            name: "历史策略",
            description: "说明",
            version_id: "v1",
            number: 1,
            source_code: "# immutable v1",
          },
        }}
      />
    </TestRouter>,
  )
  expect(screen.getByRole("heading", { name: "实盘实例 我的实盘" })).toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "策略与启动配置" }))
  expect(screen.getByText("初始资金：2000.25")).toBeInTheDocument()
  expect(screen.getByText("通知渠道：个人推送")).toBeInTheDocument()
  expect(screen.getByRole("link", { name: "查看或编辑此策略版本" })).toHaveAttribute(
    "href",
    "/strategies/s/versions/v1",
  )
  fireEvent.click(screen.getByRole("button", { name: "预览策略代码" }))
  expect(await screen.findByRole("textbox", { name: "策略代码预览" })).toHaveValue("# immutable v1")
})

it("慢估值不阻塞建议与资金，投递独立失败并可重试", async () => {
  vi.mocked(getLivePortfolio).mockReturnValue(new Promise(() => {}))
  vi.mocked(getLiveDeliveries)
    .mockRejectedValueOnce(new Error("投递读取失败"))
    .mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 20 })
  render(
    <TestRouter>
      <LiveDetailPage
        progressive
        instance={{
          ...instance,
          balances: {
            cash: "100",
            available_cash: "80",
            reserved_cash: "20",
            positions: {},
            reserved_positions: {},
            capital_pool: "100",
          },
        }}
      />
    </TestRouter>,
  )
  expect(screen.getByRole("button", { name: "接受建议" })).toBeInTheDocument()
  expect(screen.getByText("80.00 元")).toBeInTheDocument()
  expect(screen.getByRole("status", { name: "正在加载收益曲线" })).toBeInTheDocument()
  await screen.findByText("投递读取失败")
  fireEvent.click(screen.getByRole("button", { name: "重试投递记录" }))
  await waitFor(() => expect(getLiveDeliveries).toHaveBeenCalledTimes(2))
  expect(getLivePortfolio).toHaveBeenCalledTimes(1)
})

function TestRouter({ children }: PropsWithChildren) {
  return (
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { actOnRecommendation, getLive, pauseLive } from "./api"
import { LiveDetailPage } from "./pages/live-detail-page"

vi.mock("./api", () => ({
  actOnRecommendation: vi.fn(),
  getLive: vi.fn(),
  pauseLive: vi.fn(),
  terminateLive: vi.fn(),
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
  it("成功后立即更新状态并禁用已处理按钮", async () => {
    vi.mocked(actOnRecommendation).mockResolvedValue(result)
    render(<LiveDetailPage instance={instance} />)
    fireEvent.click(screen.getByRole("button", { name: "快速确认" }))
    await waitFor(() => expect(screen.getByRole("button", { name: "快速确认" })).toBeDisabled())
    expect(await screen.findByText(/测试建议.*已确认/)).toBeInTheDocument()
    expect(actOnRecommendation).toHaveBeenCalledTimes(1)
  })
  it("显示失败原因，相同请求重试保持幂等键", async () => {
    vi.mocked(actOnRecommendation)
      .mockRejectedValueOnce(new Error("账本产生负现金"))
      .mockResolvedValueOnce(result)
    vi.mocked(getLive).mockResolvedValue(instance)
    render(<LiveDetailPage instance={instance} />)
    fireEvent.click(screen.getByRole("button", { name: "快速确认" }))
    await screen.findByText("账本产生负现金")
    await waitFor(() => expect(screen.getByRole("button", { name: "快速确认" })).toBeEnabled())
    fireEvent.click(screen.getByRole("button", { name: "快速确认" }))
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
    render(<LiveDetailPage instance={instance} />)
    const button = screen.getByRole("button", { name: "快速确认" })
    fireEvent.click(button)
    fireEvent.click(button)
    expect(actOnRecommendation).toHaveBeenCalledTimes(1)
    expect(screen.getByRole("status")).toHaveTextContent("正在处理")
    resolve(result)
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument())
  })
  it("暂停更新不丢失已加载建议", async () => {
    vi.mocked(pauseLive).mockResolvedValue({
      id: instance.id,
      backtest_id: instance.backtest_id,
      strategy_version_id: instance.strategy_version_id,
      status: "paused",
      next_decision_at: instance.next_decision_at,
    })
    render(<LiveDetailPage instance={instance} />)
    fireEvent.click(screen.getByRole("button", { name: "暂停" }))
    await screen.findByText("状态：已暂停")
    expect(screen.getByText(/测试建议/)).toBeInTheDocument()
  })
})

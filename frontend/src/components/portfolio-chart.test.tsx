import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"

import { apiRequest } from "@/lib/api/client"

import { CollapsedDescription } from "./collapsed-description"
import { PortfolioChart } from "./portfolio-chart"

vi.mock("@/lib/api/client", () => ({ apiRequest: vi.fn() }))
afterEach(() => {
  cleanup()
  vi.resetAllMocks()
})
const series = [
  {
    id: "main",
    name: "组合",
    points: [
      { day: "2026-10-21", amount: "1000", return_rate: "0" },
      { day: "2026-10-22", amount: "1100", return_rate: "0.1" },
    ],
  },
]

it("切换单位、临时添加移除与失败后重试；实盘无回测来源", async () => {
  vi.mocked(apiRequest)
    .mockResolvedValueOnce([{ id: "sh000300", name: "沪深300" }])
    .mockRejectedValueOnce(new Error("缺少行情"))
    .mockResolvedValueOnce({ id: "instrument:sh000300", name: "沪深300", points: series[0].points })
  render(<PortfolioChart kind="live" resourceId="l" series={series} amountLabel="累计收益" />)
  fireEvent.click(screen.getByRole("radio", { name: "收益率（%）" }))
  expect(screen.getByRole("img")).toHaveAccessibleName(/单位为%/)
  fireEvent.click(screen.getByRole("button", { name: "添加对比" }))
  expect(screen.queryByRole("combobox", { name: "对比来源" })).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText("搜索对比对象"), { target: { value: "沪深300" } })
  fireEvent.click(screen.getByRole("button", { name: "搜索" }))
  fireEvent.click(await screen.findByRole("button", { name: "沪深300 · sh000300" }))
  await screen.findByText("缺少行情")
  fireEvent.click(screen.getByRole("button", { name: "沪深300 · sh000300" }))
  const remove = await screen.findByRole("button", { name: "移除对比 沪深300" })
  expect(apiRequest).toHaveBeenLastCalledWith("/chart-comparisons/live/l/series?symbol=sh000300")
  fireEvent.click(remove)
  await waitFor(() =>
    expect(screen.queryByRole("button", { name: "移除对比 沪深300" })).not.toBeInTheDocument(),
  )
})

it("长说明只显示15字，悬停和点击显示全文", async () => {
  const text = "这是超过十五个字的完整操作建议说明内容，用于核对。"
  render(<CollapsedDescription text={text} />)
  const trigger = screen.getByRole("button", { name: /^查看完整说明/ })
  expect(trigger).toHaveTextContent(Array.from(text).slice(0, 15).join("") + "…")
  fireEvent.mouseEnter(trigger)
  expect(await screen.findByText(text)).toBeInTheDocument()
  fireEvent.click(trigger)
  expect(screen.getByText(text)).toBeInTheDocument()
})

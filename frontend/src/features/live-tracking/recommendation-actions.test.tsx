import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { RecommendationActions } from "./components/recommendation-actions"

describe("建议处理", () => {
  it("提供确认、拒绝与修正表单", async () => {
    const submit = vi.fn()
    render(
      <RecommendationActions
        recommendation={{
          id: "r",
          instrument_id: "000001",
          action: "buy",
          quantity: "100",
          suggested_price: "10",
          suggested_fee: "0.3",
          status: "pending",
          version: 0,
          reason: "test",
        }}
        onSubmit={submit}
      />,
    )
    fireEvent.click(screen.getByRole("button", { name: "快速确认" }))
    expect(submit).toHaveBeenCalledWith("confirm")
    expect(screen.getByRole("button", { name: "拒绝建议" })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole("button", { name: "修正成交" })).toBeEnabled())
    fireEvent.click(screen.getByText("修正成交"))
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(screen.queryByLabelText("实际标的")).not.toBeInTheDocument()
    expect(screen.queryByLabelText("实际方向")).not.toBeInTheDocument()
    expect(screen.getByLabelText("实际数量")).toHaveValue(100)
    expect(screen.getByLabelText("实际数量")).toHaveAttribute("step", "100")
    expect(screen.getByLabelText("实际价格")).toHaveValue(10)
    expect(screen.getByLabelText("手续费")).toHaveValue(0.3)
    expect(screen.getByLabelText("实际价格")).toBeRequired()
    expect(screen.getByRole("button", { name: "提交修正" })).toBeInTheDocument()
  })
})

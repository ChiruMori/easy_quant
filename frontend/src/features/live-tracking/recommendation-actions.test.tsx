import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { RecommendationActions } from "./components/recommendation-actions"

describe("建议处理", () => {
  it("提供确认、拒绝与修正表单", () => {
    const submit = vi.fn()
    render(<RecommendationActions onSubmit={submit} />)
    fireEvent.click(screen.getByRole("button", { name: "快速确认" }))
    expect(submit).toHaveBeenCalledWith("confirm")
    expect(screen.getByRole("button", { name: "拒绝建议" })).toBeInTheDocument()
    fireEvent.click(screen.getByText("修正成交"))
    expect(screen.getByLabelText("实际价格")).toBeRequired()
    expect(screen.getByRole("button", { name: "提交修正" })).toBeInTheDocument()
  })
})

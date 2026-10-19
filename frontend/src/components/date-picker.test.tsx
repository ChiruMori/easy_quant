import { cleanup, fireEvent, render, screen, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { DatePicker } from "./date-picker"

afterEach(cleanup)

describe("共享日期选择器", () => {
  it("保留表单字段、中文日历和日期回调", () => {
    const change = vi.fn()
    const { container } = render(
      <form>
        <label htmlFor="day">交易日</label>
        <DatePicker id="day" name="day" defaultValue="2026-09-29" onValueChange={change} required />
      </form>,
    )
    expect(new FormData(container.querySelector("form")!).get("day")).toBe("2026-09-29")
    fireEvent.click(screen.getByRole("button", { name: "选择日期 day" }))
    expect(screen.getByRole("grid")).toBeInTheDocument()
    const nextDay = within(screen.getByRole("grid")).getByRole("button", { name: /30/ })
    expect(nextDay).not.toBeNull()
    fireEvent.click(nextDay!)
    expect(change).toHaveBeenLastCalledWith("2026-09-30")
    expect(screen.getByLabelText("交易日")).toHaveValue("2026-09-30")
    expect(screen.queryByRole("grid")).not.toBeInTheDocument()
  })

  it("禁止无效日期提交，支持手动输入和清空", () => {
    render(<DatePicker aria-label="日期" required />)
    const input = screen.getByLabelText("日期") as HTMLInputElement
    fireEvent.change(input, { target: { value: "2026-02-30" } })
    fireEvent.blur(input)
    expect(input.checkValidity()).toBe(false)
    fireEvent.input(input, { target: { value: "2026-02-28" } })
    fireEvent.blur(input)
    expect(input.checkValidity()).toBe(true)
    fireEvent.change(input, { target: { value: "" } })
    expect(input.checkValidity()).toBe(false)
  })
})

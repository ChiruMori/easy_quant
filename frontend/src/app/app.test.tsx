import { render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { App } from "./app"

describe("App", () => {
  afterEach(() => vi.unstubAllGlobals())

  it("确认身份期间阻止访问主界面", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => undefined)),
    )
    render(<App />)
    expect(screen.getByLabelText("正在确认登录状态")).toBeInTheDocument()
  })
})

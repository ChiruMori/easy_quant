import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { useState } from "react"
import { afterEach, expect, it, vi } from "vitest"

import { CodeWorkspace } from "./code-workspace"

const loading = vi.hoisted(() => ({ fail: true }))
vi.mock("@/components/monaco-surface", () => ({
  default: ({ value, readOnly }: { value: string; readOnly: boolean }) => {
    if (loading.fail) throw new Error("offline chunk")
    return <textarea aria-label="策略代码预览" readOnly={readOnly} value={value} />
  },
}))
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})
it("编辑器加载失败保留草稿，基础文本仍可编辑并重试加载", async () => {
  vi.spyOn(console, "error").mockImplementation(() => {})
  function Draft() {
    const [value, setValue] = useState("# unsaved draft")
    return <CodeWorkspace value={value} onChange={setValue} readOnly={false} />
  }
  render(<Draft />)
  const fallback = await screen.findByRole("textbox", { name: "基础代码视图" })
  expect(fallback).toHaveValue("# unsaved draft")
  fireEvent.change(fallback, { target: { value: "# revised draft" } })
  loading.fail = false
  fireEvent.click(screen.getByRole("button", { name: "重试加载编辑器" }))
  expect(await screen.findByRole("textbox", { name: "策略代码预览" })).toHaveValue(
    "# revised draft",
  )
})

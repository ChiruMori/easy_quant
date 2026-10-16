import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"

import { SourceToggleForm } from "./source-toggle-form"

afterEach(cleanup)

it("切换立即保存，保存中阻止重复提交，失败恢复原配置", async () => {
  let rejectSave!: (error: Error) => void
  const onSave = vi.fn(
    () =>
      new Promise<void>((_, reject) => {
        rejectSave = reject
      }),
  )
  render(
    <SourceToggleForm
      sources={[{ key: "akshare", name: "AKShare", enabled: true }]}
      onSave={onSave}
    />,
  )
  fireEvent.click(screen.getByRole("button", { name: "AKShare 已启用" }))
  const button = screen.getByRole("button", { name: "AKShare 已停用" })
  expect(button).toBeDisabled()
  fireEvent.click(button)
  expect(onSave).toHaveBeenCalledTimes(1)
  expect(onSave).toHaveBeenCalledWith([{ key: "akshare", name: "AKShare", enabled: false }])
  rejectSave(new Error("网络不可用"))
  expect(await screen.findByRole("alert")).toHaveTextContent("已恢复原配置")
  expect(screen.getByRole("button", { name: "AKShare 已启用" })).toHaveAttribute(
    "aria-pressed",
    "true",
  )
})

it("保存成功保留新的启用状态", async () => {
  const onSave = vi.fn().mockResolvedValue(undefined)
  render(
    <SourceToggleForm
      sources={[{ key: "tencent", name: "腾讯", enabled: false }]}
      onSave={onSave}
    />,
  )
  fireEvent.click(screen.getByRole("button", { name: "腾讯 已停用" }))
  await waitFor(() => expect(screen.getByRole("button", { name: "腾讯 已启用" })).toBeEnabled())
  expect(screen.queryByRole("alert")).not.toBeInTheDocument()
})

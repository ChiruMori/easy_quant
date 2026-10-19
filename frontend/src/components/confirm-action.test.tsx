import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { ConfirmAction } from "./confirm-action"

afterEach(cleanup)

describe("二次确认", () => {
  it("预检、取消均不执行删除；失败保留弹窗并可重试", async () => {
    const action = vi
      .fn()
      .mockRejectedValueOnce(new Error("新增关联实盘：稳健组合，不可删除"))
      .mockResolvedValueOnce(undefined)
    const prepare = vi.fn().mockResolvedValue("关联 2 次快测和 3 次回测")
    render(
      <ConfirmAction
        label="删除策略"
        title="删除策略？"
        description="不可恢复。"
        prepare={prepare}
        action={action}
      />,
    )
    fireEvent.click(screen.getByRole("button", { name: "删除策略" }))
    expect(await screen.findByText(/关联 2 次快测和 3 次回测/)).toBeInTheDocument()
    expect(action).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole("button", { name: "取消" }))
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "删除策略" }))
    await waitFor(() => expect(screen.getByRole("button", { name: "确认删除策略" })).toBeEnabled())
    fireEvent.click(screen.getByRole("button", { name: "确认删除策略" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("稳健组合")
    expect(screen.getByRole("alertdialog")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "确认删除策略" }))
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument())
    expect(action).toHaveBeenCalledTimes(2)
  })

  it("预检失败阻止提交并显示具体关联名称", async () => {
    const action = vi.fn()
    render(
      <ConfirmAction
        label="删除渠道"
        title="删除渠道？"
        description="不可恢复"
        prepare={async () => {
          throw new Error("被实盘 长期组合 使用")
        }}
        action={action}
      />,
    )
    fireEvent.click(screen.getByRole("button", { name: "删除渠道" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("长期组合")
    expect(screen.getByRole("button", { name: "确认删除渠道" })).toBeDisabled()
    expect(action).not.toHaveBeenCalled()
  })

  it("提交期间禁止重复请求和关闭", async () => {
    let resolve!: () => void
    const action = vi.fn(
      () =>
        new Promise<void>((done) => {
          resolve = done
        }),
    )
    render(
      <ConfirmAction label="删除实盘" title="删除实盘？" description="不可恢复" action={action} />,
    )
    fireEvent.click(screen.getByRole("button", { name: "删除实盘" }))
    const confirm = screen.getByRole("button", { name: "确认删除实盘" })
    fireEvent.click(confirm)
    fireEvent.click(confirm)
    expect(action).toHaveBeenCalledTimes(1)
    expect(screen.getByRole("button", { name: "取消" })).toBeDisabled()
    resolve()
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument())
  })
})

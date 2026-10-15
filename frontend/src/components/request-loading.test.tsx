import { act, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { apiRequest, getPendingWrites } from "@/lib/api/client"

import { RequestLoading } from "./request-loading"

afterEach(() => vi.unstubAllGlobals())

describe("统一请求加载反馈", () => {
  it("阻断写请求，网络错误也释放蒙版；后台读请求不阻塞", async () => {
    let resolve!: (value: Response) => void
    let reject!: (error: Error) => void
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise<Response>((yes, no) => {
            resolve = yes
            reject = no
          }),
      ),
    )
    render(<RequestLoading />)
    let read!: Promise<unknown>
    act(() => {
      read = apiRequest("/backtests")
    })
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument()
    await act(async () => {
      resolve(new Response('{"data": []}'))
      await read
    })
    let write!: Promise<unknown>
    act(() => {
      write = apiRequest("/backtests", { method: "POST" }).catch((error) => error)
    })
    expect(await screen.findByRole("alertdialog")).toBeVisible()
    expect(screen.getByRole("status")).toHaveTextContent("请求完成后")
    expect(getPendingWrites()).toBe(1)
    await act(async () => {
      reject(new Error("离线网络失败"))
      await write
    })
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument())
    expect(getPendingWrites()).toBe(0)
  })

  it("并行请求需全部完成才关闭，并覆盖响应解析失败", async () => {
    const resolvers: Array<(value: Response) => void> = []
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>((resolve) => resolvers.push(resolve))),
    )
    render(<RequestLoading />)
    let first!: Promise<unknown>
    let second!: Promise<unknown>
    act(() => {
      first = apiRequest("/backtests", { method: "POST" })
      second = apiRequest("/admin/schedules/x", { method: "PATCH" }).catch((error) => error)
    })
    expect(getPendingWrites()).toBe(2)
    await act(async () => {
      resolvers[0](new Response('{"data": {}}'))
      await first
    })
    expect(screen.getByRole("alertdialog")).toBeVisible()
    await act(async () => {
      resolvers[1](new Response("bad-json"))
      await second
    })
    expect(getPendingWrites()).toBe(0)
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument()
  })
})

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type * as StrategyApi from "./api"

const controls = vi.hoisted(() => ({
  listWorkspace: vi.fn(),
  getStrategyVersion: vi.fn(),
  forkStrategyVersion: vi.fn(),
  createStrategy: vi.fn(),
  saveStrategyDraft: vi.fn(),
  quickTestEditor: vi.fn(),
  getQuickTest: vi.fn(),
}))
vi.mock("./components/strategy-editor", () => ({
  StrategyEditor: ({ value, onChange }: { value: string; onChange: (value: string) => void }) => (
    <textarea
      aria-label="策略代码编辑器"
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  ),
}))
vi.mock("./api", async (original) => ({
  ...(await original<typeof StrategyApi>()),
  ...controls,
  listStrategyTemplates: async () => [
    { key: "demo", name: "正预期示例", source_code: "# example" },
  ],
}))
vi.mock("@/lib/api/client", () => ({
  apiRequest: async () => [
    {
      key: "context.position",
      name: "持仓数量",
      signature: "context.position(symbol)",
      description: "查询持仓",
      parameters: "股票代码",
      output: "数量",
      example: "context.position('000001')",
      runtime: "all",
    },
  ],
}))

import { StrategiesPage } from "./pages/strategies-page"
import { StrategyDetailPage } from "./pages/strategy-detail-page"
import { BLANK_STRATEGY, StrategyEditPage } from "./pages/strategy-edit-page"

const draft = {
  id: "s",
  version_id: "v1",
  name: "草稿策略",
  description: "",
  number: 1,
  state: "draft",
  revision: 0,
  source_code: "# saved",
  created_at: "2026-09-29T00:00:00Z",
  live_instances: [],
}
const locked = { ...draft, id: "locked", version_id: "v0", name: "锁定策略", state: "testing" }
function mount(path = "/strategies") {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/strategies" element={<StrategiesPage />} />
          <Route path="/strategies/new" element={<StrategyEditPage />} />
          <Route
            path="/strategies/:strategyId/versions/:versionId"
            element={<StrategyDetailPage />}
          />
          <Route
            path="/strategies/:strategyId/versions/:versionId/edit"
            element={<StrategyEditPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}
afterEach(cleanup)
beforeEach(() => {
  vi.clearAllMocks()
  controls.listWorkspace.mockResolvedValue({
    items: [draft, locked],
    total: 41,
    page: 1,
    page_size: 20,
  })
  controls.getStrategyVersion.mockResolvedValue(draft)
  controls.forkStrategyVersion.mockResolvedValue({ ...draft, version_id: "v2", number: 2 })
  controls.getQuickTest.mockResolvedValue({
    id: "job",
    status: "succeeded",
    trading_day: "2026-09-29",
    phase_results: [],
  })
  controls.quickTestEditor.mockResolvedValue({
    id: "job",
    status: "queued",
    trading_day: "2026-09-29",
    phase_results: [],
  })
})

describe("策略工作台", () => {
  it("默认列表无编辑器，按版本分页并提供图标 CRUD", async () => {
    mount()
    expect(await screen.findByText("草稿策略")).toBeInTheDocument()
    expect(screen.queryByLabelText("策略代码编辑器")).not.toBeInTheDocument()
    expect(screen.getByRole("link", { name: "新建策略" })).toHaveAttribute(
      "href",
      "/strategies/new",
    )
    expect(screen.getByRole("link", { name: "编辑 草稿策略 v1" })).toBeInTheDocument()
    fireEvent.click(screen.getByRole("link", { name: "第 2 页" }))
    await waitFor(() => expect(controls.listWorkspace).toHaveBeenLastCalledWith(2, "", ""))
    fireEvent.change(screen.getByRole("textbox", { name: "搜索策略" }), {
      target: { value: "草稿" },
    })
    fireEvent.click(screen.getByRole("button", { name: "搜索策略" }))
    await waitFor(() => expect(controls.listWorkspace).toHaveBeenLastCalledWith(1, "草稿", ""))
  })

  it("锁定版本编辑先确认，取消不创建，确认后新草稿可编辑", async () => {
    mount()
    fireEvent.click(await screen.findByRole("button", { name: "编辑 锁定策略 v1" }))
    expect(screen.getByRole("alertdialog")).toHaveTextContent("原策略代码、回测及实盘引用保持不变")
    expect(controls.forkStrategyVersion).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole("button", { name: "取消" }))
    fireEvent.click(screen.getByRole("button", { name: "编辑 锁定策略 v1" }))
    fireEvent.click(screen.getByRole("button", { name: "确认创建草稿版本" }))
    await waitFor(() => expect(controls.forkStrategyVersion).toHaveBeenCalledWith("locked", "v0"))
    expect(await screen.findByLabelText("策略代码编辑器")).toHaveValue("# saved")
  })

  it("新建默认空白，所有模板均确认后覆盖，公共库默认折叠", async () => {
    mount("/strategies/new")
    expect(screen.getByLabelText("策略代码编辑器")).toHaveValue(BLANK_STRATEGY)
    fireEvent.change(screen.getByLabelText("策略代码编辑器"), { target: { value: "# unfinished" } })
    fireEvent.keyDown(screen.getByRole("button", { name: "代码模板" }), { key: "ArrowDown" })
    fireEvent.click(await screen.findByRole("menuitem", { name: "使用正预期示例" }))
    expect(screen.getByLabelText("策略代码编辑器")).toHaveValue("# unfinished")
    fireEvent.click(screen.getByRole("button", { name: "取消" }))
    expect(screen.getByLabelText("策略代码编辑器")).toHaveValue("# unfinished")
    fireEvent.keyDown(screen.getByRole("button", { name: "代码模板" }), { key: "ArrowDown" })
    fireEvent.click(await screen.findByRole("menuitem", { name: "使用正预期示例" }))
    fireEvent.click(screen.getByRole("button", { name: "确认替换模板" }))
    expect(screen.getByLabelText("策略代码编辑器")).toHaveValue("# example")
    const entry = await screen.findByRole("button", { name: /持仓数量/ })
    expect(entry).toHaveAttribute("aria-expanded", "false")
    expect(screen.queryByText("context.position(symbol)")).not.toBeInTheDocument()
    fireEvent.click(entry)
    expect(screen.getByText("context.position(symbol)")).toBeVisible()
  })

  it("快测运行未保存内容，不调用策略保存接口", async () => {
    mount("/strategies/new")
    fireEvent.change(screen.getByLabelText("快速测试交易日"), { target: { value: "2026-09-29" } })
    fireEvent.change(screen.getByLabelText("策略代码编辑器"), {
      target: { value: "# current editor" },
    })
    fireEvent.click(screen.getByRole("button", { name: "运行快速测试" }))
    await waitFor(() =>
      expect(controls.quickTestEditor).toHaveBeenCalledWith({
        source_code: "# current editor",
        trading_day: "2026-09-29",
        allow_mock: false,
      }),
    )
    expect(controls.createStrategy).not.toHaveBeenCalled()
    expect(controls.saveStrategyDraft).not.toHaveBeenCalled()
    expect(screen.getByText(/不保存代码快照/)).toBeInTheDocument()
  })

  it("草稿保存失败保留内容与修订号，详情中的锁定版本也提示复制", async () => {
    controls.saveStrategyDraft.mockRejectedValue(new Error("策略已变化，请重新加载"))
    mount("/strategies/s/versions/v1/edit")
    fireEvent.change(await screen.findByLabelText("策略代码编辑器"), {
      target: { value: "# unsaved" },
    })
    fireEvent.click(screen.getByRole("button", { name: "保存草稿" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("策略已变化")
    expect(screen.getByLabelText("策略代码编辑器")).toHaveValue("# unsaved")
    expect(controls.saveStrategyDraft).toHaveBeenCalledWith(
      "s",
      "v1",
      expect.objectContaining({ expected_revision: 0, source_code: "# unsaved" }),
    )
    cleanup()
    controls.getStrategyVersion.mockResolvedValue(locked)
    mount("/strategies/locked/versions/v0")
    fireEvent.click(await screen.findByRole("button", { name: "编辑 锁定策略 v1" }))
    expect(screen.getByRole("alertdialog")).toHaveTextContent("创建新的草稿")
  })
})

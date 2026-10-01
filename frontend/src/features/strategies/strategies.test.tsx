import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("../strategies/components/strategy-editor", () => ({
  StrategyEditor: () => <div aria-label="策略代码编辑器" />,
}))
vi.mock("./api", () => ({
  listStrategies: async () => [],
  listStrategyTemplates: async () => [
    {
      key: "positive-expectation",
      name: "正预期示例",
      source_code:
        "def before_market(context, parameters):\n    return []\n" +
        "def on_market(context, parameters):\n    return []\n" +
        "def after_market(context, parameters):\n    return []",
    },
  ],
  createStrategy: vi.fn(),
  addStrategyVersion: vi.fn(),
  runStrategy: vi.fn(),
}))
import { StrategiesPage } from "./pages/strategies-page"

describe("策略页面", () => {
  it("提供示例、编辑和运行输出入口但不提供调试控件", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <StrategiesPage />
      </QueryClientProvider>,
    )
    expect(await screen.findByText("使用正预期示例")).toBeInTheDocument()
    expect(screen.queryByText(/断点|单步调试/)).not.toBeInTheDocument()
  })
})

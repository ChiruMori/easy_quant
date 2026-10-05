import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { FactorCatalogPage } from "./pages/factor-catalog-page"
import { FactorDetailPage } from "./pages/factor-detail-page"

describe("只读因子文档", () => {
  it("展示调用示例且没有管理入口", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <FactorCatalogPage
          factors={[
            {
              key: "technical.ma",
              name: "5 日均线",
              description: "均线因子",
              parameters: { window: "窗口" },
              output: "数值",
              example: "factor('technical.ma')",
              output_example: "{'available': True, 'value': Decimal('10.50'), 'window': 5}",
            },
          ]}
        />
        <FactorDetailPage
          factor={{
            key: "technical.ma",
            name: "均线",
            description: "均线因子",
            parameters: { window: "窗口" },
            output: "数值",
            example: "factor('technical.ma')",
            output_example: "{'available': True, 'value': Decimal('10.50'), 'window': 5}",
          }}
        />
      </QueryClientProvider>,
    )
    expect(screen.getByText("factor('technical.ma')")).toBeInTheDocument()
    expect(screen.getAllByText(/'available': True/)).toHaveLength(2)
    expect(screen.queryByText(/新增|删除|训练|上传|发布/)).not.toBeInTheDocument()
  })
})

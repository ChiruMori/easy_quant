import { describe, expect, it } from "vitest"

import { businessFlow } from "./business-flow-data"

const row = (id: string, revenue: string, cost: string | null, profit: string) => ({
  record_key: id,
  available_at: "2026-01-01T00:00:00+08:00",
  item_name: id,
  business_revenue: revenue,
  business_cost: cost,
  business_profit: profit,
})

describe("主营收支展示", () => {
  it("仅汇总真实且平衡的收入成本利润，不叠加零值节点", () => {
    const model = businessFlow([
      row("产品甲", "100000000", "60000000", "40000000"),
      row("产品乙", "200000000", "150000000", "50000000"),
      row("零值", "0", "0", "0"),
    ])
    expect(model.flow?.links).toEqual([
      { source: 0, target: 2, value: 1 },
      { source: 1, target: 2, value: 2 },
      { source: 2, target: 3, value: 2.1 },
      { source: 2, target: 4, value: 0.9 },
    ])
    expect(model.points).toHaveLength(3)
  })
  it.each([
    [row("缺失", "100000000", null, "40000000"), "缺失指标"],
    [row("亏损", "100000000", "120000000", "-20000000"), "亏损"],
    [row("差额", "100000000", "60000000", "30000000"), "不一致"],
    [row("零值", "0", "0", "0"), "均为零"],
  ])("缺失、亏损或不平衡不伪造桑基流量", (item, reason) => {
    const model = businessFlow([item])
    expect(model.flow).toBeNull()
    expect(model.reason).toContain(reason)
    expect(model.points[0].business_cost).toBe(
      item.business_cost === null ? null : Number(item.business_cost) / 1e8,
    )
    expect(model.points[0].business_profit).toBe(Number(item.business_profit) / 1e8)
  })
  it("Decimal校验避免浮点误判，跨币种不汇总", () => {
    expect(businessFlow([row("小数", "0.3", "0.1", "0.2")]).flow).not.toBeNull()
    expect(
      businessFlow([
        { ...row("甲", "3", "1", "2"), currency: "CNY" },
        { ...row("乙", "3", "1", "2"), currency: "USD" },
      ]).flow,
    ).toBeNull()
  })
  it("汇总行与明细并存时保留原始项目，不重复累加", () => {
    const model = businessFlow([row("产品", "3", "1", "2"), row("合计", "3", "1", "2")])
    expect(model.flow).toBeNull()
    expect(model.reason).toContain("避免重复汇总")
    expect(model.points).toHaveLength(2)
  })
})

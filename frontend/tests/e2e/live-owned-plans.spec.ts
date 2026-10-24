import { expect, test } from "@playwright/test"

for (const width of [1440, 360]) {
  test(`实盘专属计划按需加载并随暂停恢复更新 ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 })
    let status = "active"
    let planReads = 0
    const portfolio = {
      cash: "1000",
      available_cash: "1000",
      reserved_cash: "0",
      positions: {},
      reserved_positions: {},
      capital_pool: "1000",
      initial_equity: "1000",
      profit: "0",
      return_rate: "0",
      missing_symbols: [],
      valuation_note: "真实行情估值",
      curve: [
        { at: "2026-10-22T08:00:00Z", profit: "0", return_rate: "0" },
        { at: "2026-10-23T08:00:00Z", profit: "0", return_rate: "0" },
      ],
    }
    await page.route("**/api/v1/**", (route) => {
      const path = new URL(route.request().url()).pathname.replace("/api/v1", "")
      if (path === "/auth/me")
        return route.fulfill({
          json: {
            data: { user: { id: "u", username: "研究员", role: "admin", status: "active" } },
          },
        })
      if (path.endsWith("/pause")) status = "paused"
      if (path.endsWith("/resume")) status = "active"
      if (path.endsWith("/portfolio")) return route.fulfill({ json: { data: portfolio } })
      if (path.endsWith("/schedules")) {
        planReads++
        return route.fulfill({
          json: {
            data: ["before_market", "on_market"].map((phase, index) => ({
              id: `p${index}`,
              task_type: "live-analysis",
              configuration: { instance_id: "owned", phase },
              schedule_expression: index ? "50 14 * * 1-5" : "0 9 * * 1-5",
              enabled: status === "active",
              timezone: "Asia/Shanghai",
              next_run_at: "2026-10-26T01:00:00Z",
            })),
          },
        })
      }
      if (path.endsWith("/deliveries"))
        return route.fulfill({ json: { data: { items: [], page: 1, total: 0, page_size: 20 } } })
      if (path.startsWith("/live-instances/"))
        return route.fulfill({
          json: {
            data: {
              id: "owned",
              name: "个人运行计划",
              status,
              backtest_id: "b",
              strategy_version_id: "v",
              next_decision_at: "",
              portfolio,
              balances: portfolio,
              operations: { items: [], page: 1, total: 0, page_size: 20 },
            },
          },
        })
      return route.fulfill({ json: { data: [] } })
    })
    await page.goto("/live/owned")
    await expect(page.getByRole("heading", { name: "实盘实例 个人运行计划" })).toBeVisible()
    expect(planReads).toBe(0)
    await page.getByRole("button", { name: "实盘运行计划", exact: true }).click()
    await expect(page.getByRole("cell", { name: "启用", exact: true })).toHaveCount(2)
    await page.getByRole("button", { name: "暂停", exact: true }).click()
    await page.getByRole("button", { name: "确认暂停", exact: true }).click()
    await expect(page.getByRole("cell", { name: "停用", exact: true })).toHaveCount(2)
    await page.getByRole("button", { name: "恢复实盘", exact: true }).click()
    await page.getByRole("button", { name: "确认恢复实盘", exact: true }).click()
    await expect(page.getByRole("cell", { name: "启用", exact: true })).toHaveCount(2)
    await expect.poll(() => planReads).toBe(3)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    )
    await page.screenshot({ path: testInfo.outputPath(`live-plans-${width}.png`), fullPage: true })
  })
}

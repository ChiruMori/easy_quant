import { expect, test } from "@playwright/test"

for (const width of [1440, 360]) {
  test(`实盘名称筛选分页、行内操作与终止冻结 ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 })
    let frozenReads = 0
    let pauseFails = true
    const rows = Array.from({ length: 24 }, (_, index) => ({
      id: `freeze-${index}`,
      name: index >= 22 ? `终止测试${index}` : `运行测试${index}`,
      status: index >= 22 ? "terminated" : "active",
      initial_cash: "1000",
      return_rate: index >= 22 ? "-0.1" : undefined,
      backtest_id: "b",
      strategy_version_id: "v",
      next_decision_at: "2026-10-24T01:00:00Z",
      balances: {
        cash: "1000",
        available_cash: "1000",
        reserved_cash: "0",
        positions: { "000001": "100" },
        reserved_positions: {},
        capital_pool: "1000",
      },
      operations: {
        items: [
          {
            id: "r",
            instrument_id: "000001",
            action: "buy",
            quantity: "100",
            reason: "待操作建议",
            status: "pending",
            version: 0,
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
      },
    }))
    await page.route("**/api/v1/**", (route) => {
      const url = new URL(route.request().url())
      const path = url.pathname.replace("/api/v1", "")
      if (path === "/auth/me")
        return route.fulfill({
          json: {
            data: { user: { id: "u", username: "研究员", role: "admin", status: "active" } },
          },
        })
      if (path === "/live-instances/freeze-0/pause" || path === "/live-instances/freeze-0/resume") {
        if (path.endsWith("/pause") && pauseFails) {
          pauseFails = false
          return route.fulfill({ status: 409, json: { error: { message: "暂停失败，请重试" } } })
        }
        rows[0].status = path.endsWith("/pause") ? "paused" : "active"
        return route.fulfill({ json: { data: rows[0] } })
      }
      if (path === "/live-instances") {
        if (!url.searchParams.has("page")) return route.fulfill({ json: { data: rows } })
        const selected = rows.filter(
          (row) =>
            row.name.includes(url.searchParams.get("search") ?? "") &&
            (!url.searchParams.get("status") || row.status === url.searchParams.get("status")),
        )
        const page = Number(url.searchParams.get("page") ?? 1)
        return route.fulfill({
          json: {
            data: {
              items: selected.slice((page - 1) * 20, page * 20),
              total: selected.length,
              page,
              page_size: 20,
            },
          },
        })
      }
      if (path.endsWith("/portfolio")) {
        if (url.searchParams.get("view") === "metrics")
          return route.fulfill({
            json: { data: { at: "2026-10-23T08:00:00Z", profit: "100", return_rate: "0.1" } },
          })
        frozenReads++
        return route.fulfill({
          json: {
            data: {
              ...rows[22].balances,
              profit: "-100",
              return_rate: "-0.1",
              missing_symbols: [],
              valuation_note: "数据冻结于终止时点，后续不再更新。",
              curve: [
                { at: "2026-10-22T08:00:00Z", profit: "0", return_rate: "0" },
                { at: "2026-10-23T08:00:00Z", profit: "-100", return_rate: "-0.1" },
              ],
            },
          },
        })
      }
      if (path.endsWith("/schedules"))
        return route.fulfill({
          json: {
            data: [
              {
                id: "historic",
                task_type: "live-analysis",
                configuration: { instance_id: "freeze-22", phase: "on_market" },
                enabled: false,
                schedule_expression: "30 10 * * 1-5",
                timezone: "Asia/Shanghai",
              },
            ],
          },
        })
      if (path.endsWith("/deliveries"))
        return route.fulfill({ json: { data: { items: [], total: 0, page: 1, page_size: 20 } } })
      if (path === "/chart-comparisons/instruments")
        return route.fulfill({ json: { data: [{ id: "sh000300", name: "沪深300" }] } })
      if (path.startsWith("/chart-comparisons/live/"))
        return route.fulfill({
          json: {
            data: {
              id: "instrument:sh000300",
              name: "沪深300",
              points: [
                { day: "2026-10-22", amount: "0", return_rate: "0" },
                { day: "2026-10-23", amount: "20", return_rate: "0.02" },
              ],
            },
          },
        })
      if (path.startsWith("/live-instances/"))
        return route.fulfill({ json: { data: rows.find((row) => path.endsWith(row.id)) } })
      return route.fulfill({ json: { data: [] } })
    })
    await page.goto("/live")
    const firstRow = page.getByRole("row").filter({ hasText: "运行测试0" })
    await firstRow.getByRole("button", { name: "暂停实盘", exact: true }).click()
    await expect(firstRow.getByRole("alert")).toBeVisible()
    await firstRow.getByRole("button", { name: "暂停实盘", exact: true }).click()
    await expect(firstRow.getByRole("button", { name: "恢复实盘", exact: true })).toBeVisible()
    await firstRow.getByRole("button", { name: "恢复实盘", exact: true }).click()
    await expect(firstRow.getByRole("button", { name: "暂停实盘", exact: true })).toBeVisible()
    await expect(page.getByRole("button", { name: /停止实盘|终止实盘/ })).toHaveCount(0)
    await expect(page.getByRole("cell", { name: "10.00%", exact: true }).first()).toBeVisible()
    const paging = page.getByRole("navigation", { name: "实盘列表分页" })
    await paging.getByRole("button", { name: "第 2 页", exact: true }).click()
    await expect(page.getByRole("link", { name: "终止测试22", exact: true })).toBeVisible()
    await page.getByLabel("搜索实盘名称").fill("终止")
    await page.getByRole("button", { name: "搜索", exact: true }).click()
    await page.getByRole("combobox", { name: "实盘状态" }).click()
    await page.getByRole("option", { name: "已终止", exact: true }).click()
    await expect(paging).toContainText("共 2 条")
    await expect(page.getByRole("cell", { name: "-10.00%", exact: true })).toHaveCount(2)
    await expect(
      page
        .getByRole("table", { name: "实盘列表" })
        .getByRole("button", { name: "删除实盘", exact: true }),
    ).toHaveCount(2)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    )
    await page.screenshot({ path: testInfo.outputPath(`live-list-${width}.png`), fullPage: true })
    await page.getByRole("link", { name: "终止测试22", exact: true }).click()
    await expect(page.getByText("实盘已终止 · 数据已冻结", { exact: true })).toBeVisible()
    for (const name of ["刷新实盘", "手动添加操作", "暂停", "终止", "接受建议"])
      await expect(page.getByRole("button", { name, exact: true })).toHaveCount(0)
    await expect(page.getByRole("region", { name: "当前收益", exact: true })).toContainText(
      "-100.00 元",
    )
    await expect(page.getByRole("region", { name: "当前收益率", exact: true })).toContainText(
      "-10.00%",
    )
    await expect(page.getByText("实盘收益曲线", { exact: true })).toBeVisible()
    await page.getByRole("tab", { name: "收益率（%）", exact: true }).click()
    await expect(page.getByRole("tab", { name: "收益率（%）", exact: true })).toHaveAttribute(
      "data-state",
      "active",
    )
    expect(frozenReads).toBe(1)
    await page.getByRole("button", { name: "添加对比", exact: true }).click()
    await page.getByLabel("搜索对比对象").fill("沪深300")
    await page.getByRole("dialog").getByRole("button", { name: "搜索", exact: true }).click()
    await page.getByRole("button", { name: "沪深300 · sh000300", exact: true }).click()
    await expect(page.getByRole("button", { name: "移除对比 沪深300", exact: true })).toBeVisible()
    await page.getByRole("button", { name: "实盘运行计划", exact: true }).click()
    await expect(
      page.getByText("已停止触发，保留终止时的计划配置。", { exact: true }),
    ).toBeVisible()
    await expect(page.getByRole("table", { name: "实盘计划列表" })).toContainText("30 10 * * 1-5")
    await expect(page.getByRole("table", { name: "实盘计划列表" }).getByRole("button")).toHaveCount(
      0,
    )
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    )
    await page.screenshot({ path: testInfo.outputPath(`live-frozen-${width}.png`), fullPage: true })
  })
}

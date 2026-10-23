import { expect, test } from "@playwright/test"

for (const width of [1440, 360]) {
  test(`回测与实盘复用曲线、临时比较与单位切换 ${width}px`, async ({ page }, testInfo) => {
    test.setTimeout(90000)
    await page.setViewportSize({ width, height: 1000 })
    await page.goto("/login")
    await page.getByLabel("用户名", { exact: true }).fill("admin")
    await page.getByLabel("密码", { exact: true }).fill("change-this-admin-password")
    await page.getByRole("button", { name: "登录", exact: true }).click()
    await expect(page).toHaveURL(/\/$/)
    const run = {
      id: "chart-v1",
      strategy_version_id: "v",
      created_at: "2026-10-21T02:00:00Z",
      status: "succeeded",
      progress: 100,
      config: { initial_cash: "100000", start_day: "2026-10-20", end_day: "2026-10-21" },
      benchmark: { symbol: "sh000300", name: "沪深300" },
      periods: [
        { trading_day: "2026-10-20", equity: "100000", benchmark_equity: "100000" },
        { trading_day: "2026-10-21", equity: "110000", benchmark_equity: "105000" },
      ],
      metrics: {},
      trades: [],
      assumptions: { commission_rate: "0.0003", slippage_rate: "0.001" },
      snapshot_id: "snapshot",
      application_version: "fixture-v1",
    }
    const live = {
      id: "chart-live-v1",
      name: "图表测试",
      status: "active",
      strategy_version_id: "v",
      backtest_id: run.id,
      next_decision_at: "",
      portfolio: {
        cash: "1000.123",
        available_cash: "987.6789",
        reserved_cash: "12.4441",
        capital_pool: "100000",
        initial_equity: "100000",
        reserved_positions: {},
        positions: {},
        profit: "12.5",
        return_rate: "0.000125",
        missing_symbols: [],
        valuation_note: "按已发布日线收盘价估值。",
        curve: [
          { at: "2026-10-20T02:00:00Z", profit: "0", return_rate: "0" },
          { at: "2026-10-21T02:00:00Z", profit: "12.5", return_rate: "0.000125" },
        ],
      },
      operations: { items: [], total: 0, page: 1, page_size: 20 },
      notification_deliveries: [
        {
          id: "delivery-v1",
          status: "retry",
          channel: "ntfy",
          attempts: 1,
          updated_at: "2026-10-21T02:00:00Z",
          error: "通知服务暂时不可用，将自动重试",
          error_code: "ntfy_transport",
        },
      ],
    }
    await page.route("**/api/v1/backtests**", (route) =>
      route.fulfill({
        json: {
          data: new URL(route.request().url()).pathname.endsWith("/stock-performance")
            ? { items: [], total: 0, page: 1, page_size: 20 }
            : new URL(route.request().url()).pathname.endsWith("/backtests")
              ? [run]
              : run,
        },
      }),
    )
    await page.route("**/api/v1/live-instances/chart-live-v1**", (route) => {
      const path = new URL(route.request().url()).pathname
      return route.fulfill({
        json: {
          data: path.endsWith("/portfolio")
            ? live.portfolio
            : path.endsWith("/deliveries")
              ? { items: live.notification_deliveries, page: 1, page_size: 20, total: 1 }
              : live,
        },
      })
    })
    let failure = true
    await page.route("**/api/v1/chart-comparisons/**", (route) => {
      const url = new URL(route.request().url())
      if (url.pathname.endsWith("/instruments"))
        return route.fulfill({ json: { data: [{ id: "000001", name: "平安银行" }] } })
      if (url.pathname.endsWith("/candidates"))
        return route.fulfill({ json: { data: [{ id: "other-chart-v1", name: "同期回测" }] } })
      if (failure) {
        failure = false
        return route.fulfill({
          status: 409,
          json: { error: { code: "state_conflict", message: "比较标的缺少起点行情" } },
        })
      }
      const other = url.searchParams.get("backtest_id")
      return route.fulfill({
        json: {
          data: {
            id: other ? "backtest:other-chart-v1" : "instrument:000001",
            name: other ? "同期回测" : "平安银行",
            points: [
              { day: "2026-10-20", amount: "100000", return_rate: "0" },
              { day: "2026-10-21", amount: "108000", return_rate: ".08" },
            ],
          },
        },
      })
    })
    await page.goto("/backtests")
    await expect(page.getByRole("columnheader", { name: "创建时间" })).toBeVisible()
    await expect(page.getByRole("cell", { name: "2026/10/21 10:00:00" })).toBeVisible()
    await page.goto("/backtests/chart-v1")
    await page.getByRole("radio", { name: "收益率（%）", exact: true }).click()
    await expect(page.getByRole("img", { name: /组合权益曲线/ })).toHaveAttribute(
      "aria-label",
      /单位为%/,
    )
    await page.getByRole("button", { name: "添加对比", exact: true }).click()
    await page.getByLabel("搜索对比对象").fill("平安银行")
    await page.getByRole("dialog").getByRole("button", { name: "搜索", exact: true }).click()
    await page.getByRole("button", { name: "平安银行 · 000001", exact: true }).click()
    await expect(page.getByRole("alert")).toContainText("缺少起点行情")
    await page.getByRole("button", { name: "平安银行 · 000001", exact: true }).click()
    await expect(page.getByRole("button", { name: "移除对比 平安银行", exact: true })).toBeVisible()
    await page.getByRole("button", { name: "添加对比", exact: true }).click()
    await page.getByRole("combobox", { name: "对比来源", exact: true }).click()
    await page.getByRole("option", { name: "相同配置的回测", exact: true }).click()
    await page.getByLabel("搜索对比对象").fill("")
    await page.getByRole("dialog").getByRole("button", { name: "搜索", exact: true }).click()
    await page.getByRole("button", { name: "同期回测", exact: true }).click()
    await expect(page.getByRole("button", { name: "移除对比 同期回测", exact: true })).toBeVisible()
    await page.getByRole("radio", { name: "金额（元）", exact: true }).click()
    const paths = page.locator(".recharts-line-curve")
    await expect(paths).toHaveCount(3)
    for (const path of await paths.all())
      expect(await path.evaluate((element) => getComputedStyle(element).stroke)).not.toBe("none")
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    )
    await page.screenshot({ path: testInfo.outputPath(`comparison-${width}.png`), fullPage: true })
    await page.reload()
    await expect(page.getByRole("button", { name: /^移除对比/ })).toHaveCount(0)
    await page.goto("/live/chart-live-v1")
    await expect(page.getByRole("region", { name: "可用资金", exact: true })).toContainText(
      "987.68 元",
    )
    await expect(page.getByRole("region", { name: "锁定资金", exact: true })).toContainText(
      "12.44 元",
    )
    await expect(page.getByRole("cell", { name: /ntfy_transport/ })).toBeVisible()
    await page.getByRole("radio", { name: "收益率（%）", exact: true }).click()
    await expect(page.getByRole("img", { name: /累计收益曲线/ })).toHaveAttribute(
      "aria-label",
      /单位为%/,
    )
    await page.getByRole("button", { name: "添加对比", exact: true }).click()
    await expect(page.getByRole("combobox", { name: "对比来源", exact: true })).toHaveCount(0)
    await page.getByLabel("搜索对比对象").fill("平安银行")
    await page.getByRole("dialog").getByRole("button", { name: "搜索", exact: true }).click()
    await page.getByRole("button", { name: "平安银行 · 000001", exact: true }).click()
    await expect(page.getByRole("button", { name: "移除对比 平安银行", exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    )
    await page.screenshot({
      path: testInfo.outputPath(`live-comparison-${width}.png`),
      fullPage: true,
    })
  })
}

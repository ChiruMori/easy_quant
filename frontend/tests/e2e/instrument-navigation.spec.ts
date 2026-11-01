import { expect, test } from "@playwright/test"

for (const width of [1440, 360]) {
  test(`回测实盘代码跳转、MA5与日期查询对齐 ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 })
    const bars = [
      "2026-09-07",
      "2026-09-08",
      "2026-09-09",
      "2026-09-10",
      "2026-09-11",
      "2026-09-14",
      "2026-09-15",
      "2026-09-16",
    ].map((day, index) => ({
      symbol: "000001",
      trading_day: day,
      open: String(10 + index),
      close: String(11 + index),
      low: String(9 + index),
      high: String(12 + index),
      volume: "1000",
    }))
    let failed = false
    const portfolio = {
      cash: "1000",
      available_cash: "1000",
      reserved_cash: "0",
      reserved_positions: {},
      positions: { "000001": "100" },
      position_values: { "000001": "1800" },
      capital_pool: "2000",
      profit: "0",
      return_rate: "0",
      valuation_note: "日线收盘估值",
      missing_symbols: [],
      curve: [],
    }
    await page.route("**/api/v1/**", (route) => {
      const url = new URL(route.request().url())
      const path = url.pathname.replace("/api/v1", "")
      if (path === "/market-data/instruments/000001/daily-bars") {
        if (url.searchParams.get("start_day") && !failed) {
          failed = true
          return route.fulfill({ status: 503, json: { error: { message: "日线查询暂时失败" } } })
        }
        return route.fulfill({
          json: {
            data: bars.filter(
              (row) =>
                (!url.searchParams.get("start_day") ||
                  row.trading_day >= url.searchParams.get("start_day")!) &&
                (!url.searchParams.get("end_day") ||
                  row.trading_day <= url.searchParams.get("end_day")!),
            ),
          },
        })
      }
      const fixtures: Record<string, unknown> = {
        "/auth/me": { user: { id: "u", username: "研究员", role: "user", status: "active" } },
        "/backtests/nav": {
          id: "nav",
          strategy_version_id: "v",
          status: "succeeded",
          progress: 100,
          snapshot_id: "s",
          application_version: "fixture",
          config: { initial_cash: "1000" },
          metrics: {},
          periods: [],
          assumptions: {},
          trades: [
            {
              trading_day: "2026-09-07",
              symbol: "000001",
              action: "buy",
              quantity: "100",
              price: "11",
              fee: "0",
            },
          ],
        },
        "/backtests/nav/stock-performance": {
          items: [
            {
              symbol: "000001",
              quantity: "100",
              realized_profit: "0",
              unrealized_profit: "0",
              profit: "0",
              market_value: "1800",
              remaining_cost: "1100",
            },
          ],
          page: 1,
          page_size: 20,
          total: 1,
        },
        "/live/nav": {
          id: "nav",
          name: "导航测试",
          backtest_id: "nav",
          strategy_version_id: "v",
          status: "active",
          next_decision_at: "",
          balances: portfolio,
          operations: {
            items: [
              {
                id: "r",
                instrument_id: "000001",
                action: "buy",
                quantity: "100",
                status: "pending",
                reason: "测试建议",
                version: 0,
              },
            ],
            total: 1,
            page: 1,
            page_size: 20,
          },
        },
        "/live-instances/nav": {
          id: "nav",
          name: "导航测试",
          backtest_id: "nav",
          strategy_version_id: "v",
          status: "active",
          next_decision_at: "",
          balances: portfolio,
          operations: {
            items: [
              {
                id: "r",
                instrument_id: "000001",
                action: "buy",
                quantity: "100",
                status: "pending",
                reason: "测试建议",
                version: 0,
              },
            ],
            total: 1,
            page: 1,
            page_size: 20,
          },
        },
        "/live-instances/nav/portfolio": portfolio,
        "/live-instances/nav/deliveries": { items: [], total: 0, page: 1, page_size: 20 },
        "/market-data/instruments/000001": {
          symbol: "000001",
          name: "平安银行",
          exchange: "深圳证券交易所",
          status: "active",
        },
      }
      return path in fixtures
        ? route.fulfill({ json: { data: fixtures[path] } })
        : route.fulfill({ status: 404, json: { error: { message: `未定义 fixture ${path}` } } })
    })
    await page.goto("/backtests/nav")
    const links = page.getByRole("link", { name: "查看 000001 股票详情", exact: true })
    await expect(links).toHaveCount(2)
    await links.last().click()
    await expect(page).toHaveURL(/\/instruments\/000001$/)
    await expect(page.getByRole("heading", { name: "000001 平安银行" })).toBeVisible()
    await expect(page.getByRole("button", { name: "标记停牌" })).toHaveCount(0)
    const chart = page.getByRole("img", { name: "可缩放和拖动的 K 线图" })
    await expect(chart.locator("canvas")).toBeVisible()
    await expect(page.getByText(/默认叠加 MA5（5日收盘均线）/)).toBeVisible()
    const box = await chart.boundingBox()
    await page.mouse.move(box!.x + 68 + ((box!.width - 92) * 4.5) / 8, box!.y + 120)
    await expect(page.getByText(/MA5（5日）：13.00/)).toBeVisible()
    const start = page.getByLabel("开始日期", { exact: true })
    const end = page.getByLabel("结束日期", { exact: true })
    const query = page.getByRole("button", { name: "查询", exact: true })
    if (width >= 640) {
      const boxes = await Promise.all([start, end, query].map((control) => control.boundingBox()))
      expect(boxes[0]!.y + boxes[0]!.height).toBeCloseTo(boxes[2]!.y + boxes[2]!.height, 0)
      expect(boxes[1]!.y + boxes[1]!.height).toBeCloseTo(boxes[2]!.y + boxes[2]!.height, 0)
    }
    await start.fill("2026-09-08")
    await end.fill("2026-09-16")
    await query.click()
    await expect(page.getByText("日线查询暂时失败", { exact: true })).toBeVisible()
    await page.getByRole("button", { name: "重试日线" }).click()
    await expect(chart.locator("canvas")).toBeVisible()
    await page.getByRole("radio", { name: "周 K" }).click()
    await expect(page.getByText(/默认叠加 MA5（5周收盘均线）/)).toBeVisible()
    await page.getByRole("radio", { name: "日 K" }).click()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    )
    await page.screenshot({ path: testInfo.outputPath(`instrument-${width}.png`), fullPage: true })
    await page.getByRole("link", { name: "返回来源页面" }).click()
    await expect(page).toHaveURL(/\/backtests\/nav$/)
    await page.goto("/live/nav")
    await expect(links).toHaveCount(2)
    await links.first().click()
    await expect(page).toHaveURL(/\/instruments\/000001$/)
    await page.getByRole("link", { name: "返回来源页面" }).click()
    await expect(page).toHaveURL(/\/live\/nav$/)
  })
}

import { expect, test } from "@playwright/test"

for (const width of [1440, 360]) {
  test(`公司行为核对失败重试与实际到账 ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 })
    let reads = 0
    let writes = 0
    const portfolio = {
      cash: "1000",
      available_cash: "1000",
      reserved_cash: "0",
      positions: {},
      reserved_positions: {},
      capital_pool: "1000",
      initial_equity: "1000",
      profit: null,
      return_rate: null,
      valuation_note: "公司行为待核对",
      missing_symbols: [],
      curve: [],
    }
    await page.route("**/api/v1/**", (route) => {
      const path = new URL(route.request().url()).pathname.replace("/api/v1", "")
      if (path === "/auth/me")
        return route.fulfill({
          json: {
            data: { user: { id: "u", username: "研究员", role: "admin", status: "active" } },
          },
        })
      if (path.endsWith("/corporate-actions/confirm")) {
        writes++
        const body = route.request().postDataJSON()
        expect(body.cash).toBe("80.00")
        expect(body.share_delta).toBe("100")
        if (writes === 1)
          return route.fulfill({ status: 409, json: { error: { message: "版本已更新，请重试" } } })
        return route.fulfill({ json: { data: {} } })
      }
      if (path.endsWith("/corporate-actions")) {
        reads++
        if (reads === 1)
          return route.fulfill({
            status: 409,
            json: { error: { message: "公司行为覆盖尚未核实" } },
          })
        return route.fulfill({
          json: {
            data:
              writes >= 2
                ? []
                : [
                    {
                      event_id: "000001:2026-09-22",
                      record_key: "event-v1",
                      symbol: "000001",
                      ex_date: "2026-09-22",
                      record_date: "2026-09-21",
                      record_quantity: "100",
                      gross_cash: "100",
                      share_delta: "100",
                      rights_ratio: "0",
                      cash_pay_date: "2026-09-24",
                      shares_listing_date: "2026-09-24",
                      settled: true,
                    },
                  ],
          },
        })
      }
      if (path.endsWith("/portfolio")) return route.fulfill({ json: { data: portfolio } })
      if (path.endsWith("/deliveries") || path.endsWith("/operations"))
        return route.fulfill({ json: { data: { items: [], total: 0, page: 1, page_size: 20 } } })
      if (path.startsWith("/live-instances/"))
        return route.fulfill({
          json: {
            data: {
              id: "owned",
              name: "权益核对",
              status: "active",
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
    await page.getByRole("button", { name: "公司行为核对", exact: true }).click()
    await expect(page.getByText("公司行为覆盖尚未核实")).toBeVisible()
    await page.getByRole("button", { name: "重新核对数据" }).click()
    await page.getByRole("button", { name: "核对实际到账" }).click()
    const dialog = page.getByRole("dialog")
    await dialog.getByLabel("实际到账净现金（元）").fill("80.00")
    await dialog.getByLabel("到账凭证说明（不填写账号或联系方式）").fill("券商到账记录摘要")
    await dialog.getByRole("button", { name: "确认到账并记账" }).click()
    await expect(dialog.getByText("版本已更新，请重试")).toBeVisible()
    await expect(dialog.getByLabel("实际到账净现金（元）")).toHaveValue("80.00")
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true)
    await page.screenshot({
      path: testInfo.outputPath(`corporate-actions-${width}.png`),
      fullPage: true,
    })
    await dialog.getByRole("button", { name: "确认到账并记账" }).click()
    await expect(dialog).not.toBeVisible()
    await expect(page.getByText("当前没有待确认权益；仅覆盖已核实的数据范围。")).toBeVisible()
    expect(writes).toBe(2)
  })
}

import { expect, test } from "@playwright/test"

for (const width of [1440, 360]) {
  test(`实盘慢估值隔离、通知分页与局部重试 ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 })
    await page.goto("/login")
    await page.getByLabel("用户名", { exact: true }).fill("admin")
    await page.getByLabel("密码", { exact: true }).fill("change-this-admin-password")
    await page.getByRole("button", { name: "登录", exact: true }).click()
    await expect(page).toHaveURL(/\/$/)
    let release: () => void = () => {}
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    let portfolioCalls = 0
    let deliveryFailed = false
    await page.route("**/api/v1/live-instances/progressive**", async (route) => {
      const url = new URL(route.request().url())
      if (url.pathname.endsWith("/portfolio")) {
        portfolioCalls++
        await gate
        return route.fulfill({
          json: {
            data: {
              cash: "1000",
              available_cash: "900",
              reserved_cash: "100",
              capital_pool: "1000",
              positions: {},
              reserved_positions: {},
              profit: "12",
              return_rate: "0.012",
              valuation_note: "按已发布行情估值",
              missing_symbols: [],
              curve: [{ at: "2026-10-23T07:00:00Z", profit: "12", return_rate: "0.012" }],
            },
          },
        })
      }
      if (url.pathname.endsWith("/deliveries")) {
        if (!deliveryFailed) {
          deliveryFailed = true
          return route.fulfill({
            status: 503,
            json: { error: { code: "unavailable", message: "投递记录暂时不可用" } },
          })
        }
        const current = Number(url.searchParams.get("page") || 1)
        return route.fulfill({
          json: {
            data: {
              page: current,
              page_size: 20,
              total: 21,
              items: [
                {
                  id: `d-${current}`,
                  channel: "ntfy",
                  status: current === 1 ? "retry" : "delivered",
                  attempts: 1,
                },
              ],
            },
          },
        })
      }
      return route.fulfill({
        json: {
          data: {
            id: "progressive",
            name: "渐进加载验证",
            status: "active",
            strategy_version_id: "v",
            backtest_id: "b",
            next_decision_at: "",
            balances: {
              cash: "1000",
              available_cash: "900",
              reserved_cash: "100",
              capital_pool: "1000",
              positions: {},
              reserved_positions: {},
            },
            operations: {
              items: [
                {
                  id: "r",
                  instrument_id: "000001",
                  action: "buy",
                  quantity: "100",
                  status: "pending",
                  version: 0,
                  reason: "验证建议",
                  operation_type: "buy_signal",
                },
              ],
              total: 1,
              page: 1,
              page_size: 20,
            },
          },
        },
      })
    })
    await page.goto("/live/progressive")
    await expect(page.getByRole("heading", { name: "实盘实例 渐进加载验证" })).toBeVisible()
    await expect(page.getByText("900.00 元", { exact: true })).toBeVisible()
    await expect(page.getByRole("status", { name: "正在加载收益曲线" })).toBeVisible()
    await page.getByRole("button", { name: "接受建议" }).click()
    await expect(page.getByRole("alertdialog")).toBeVisible()
    await page.getByRole("button", { name: "取消", exact: true }).click()
    await expect(page.getByText("投递记录暂时不可用")).toBeVisible()
    await page.getByRole("button", { name: "重试投递记录" }).click()
    const pagination = page.getByRole("navigation", { name: "实盘投递分页" })
    await pagination.getByRole("button", { name: "下一页" }).click()
    await expect(pagination).toContainText("第 2 / 2 页")
    await expect(page.getByRole("cell", { name: "渠道已接收", exact: true })).toBeVisible()
    expect(portfolioCalls).toBe(1)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    )
    await page.screenshot({ path: testInfo.outputPath(`progressive-${width}.png`), fullPage: true })
    release()
    await expect(page.getByText("12.00 元", { exact: true })).toBeVisible()
    await expect(page.getByRole("status", { name: "正在加载收益曲线" })).toHaveCount(0)
    expect((await page.request.get("/brand/eq.png")).status()).toBe(200)
  })
}

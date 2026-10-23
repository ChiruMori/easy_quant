import { expect, test } from "@playwright/test"

for (const width of [1440, 360]) {
  test(`回测收益排名与通知渠道编辑分页 ${width}px`, async ({ page }, testInfo) => {
    test.setTimeout(120000)
    await page.setViewportSize({ width, height: 1000 })
    await page.goto("/login")
    await page.getByLabel("用户名", { exact: true }).fill("admin")
    await page.getByLabel("密码", { exact: true }).fill("change-this-admin-password")
    await page.getByRole("button", { name: "登录", exact: true }).click()
    await expect(page).toHaveURL(/\/$/)
    const run = {
      id: "named-run",
      name: "十月策略验证",
      strategy_version_id: "v",
      status: "succeeded",
      progress: 100,
      config: { initial_cash: "100000" },
      metrics: { cumulative_return: "0.01" },
      periods: [{ trading_day: "2026-10-21", equity: "101000" }],
      trades: [],
      assumptions: { fee_rate: "0.0003", slippage_rate: "0.0001" },
      snapshot_id: "fixture-snapshot",
      application_version: "fixture-v1",
    }
    await page.route("**/api/v1/backtests/named-run**", (route) => {
      const url = new URL(route.request().url())
      if (url.pathname.endsWith("stock-performance")) {
        const current = Number(url.searchParams.get("page") || 1)
        return route.fulfill({
          json: {
            data: {
              items: [
                {
                  symbol: current === 1 ? "000001" : "000021",
                  quantity: current === 1 ? "100" : "0",
                  remaining_cost: "1000",
                  market_value: "1200",
                  realized_profit: "100",
                  unrealized_profit: current === 1 ? "200" : "0",
                  profit: current === 1 ? "300" : "100",
                },
              ],
              page: current,
              page_size: 20,
              total: 21,
            },
          },
        })
      }
      return route.fulfill({ json: { data: run } })
    })
    await page.goto("/backtests/named-run")
    await expect(page.getByRole("heading", { name: "回测详情 · 十月策略验证" })).toBeVisible()
    await expect(page.getByRole("radio", { name: "金额（元）" })).toHaveText("￥")
    await expect(page.getByRole("radio", { name: "收益率（%）" })).toHaveText("%")
    await expect(page.getByRole("table", { name: "股票收益明细" })).toContainText("300.00")
    await page
      .getByRole("navigation", { name: "股票收益分页" })
      .getByRole("button", { name: "下一页" })
      .click()
    await expect(page.getByRole("table", { name: "股票收益明细" })).toContainText("已清仓")
    await expect(page.getByRole("cell", { name: "000021", exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    )
    await page.screenshot({ path: testInfo.outputPath(`attribution-${width}.png`), fullPage: true })

    let item = {
      id: "disabled-fixture",
      name: "停用提醒",
      channel: "ntfy",
      enabled: false,
      destination: "***",
    }
    let failSave = true
    let failDeliveries = true
    let saved: Record<string, unknown> | undefined
    await page.route("**/api/v1/notifications/**", (route) => {
      const url = new URL(route.request().url())
      const current = Number(url.searchParams.get("page") || 1)
      if (route.request().method() === "PATCH") {
        if (failSave) {
          failSave = false
          return route.fulfill({
            status: 409,
            json: { error: { code: "state_conflict", message: "保存暂时失败，请重试" } },
          })
        }
        saved = route.request().postDataJSON()
        item = { ...item, name: String(saved!.name) }
        return route.fulfill({ json: { data: item } })
      }
      if (url.pathname.endsWith("/subscriptions"))
        return route.fulfill({
          json: {
            data: {
              items: [current === 1 ? item : { ...item, id: "second", name: "第二页渠道" }],
              page: current,
              page_size: 10,
              total: 11,
            },
          },
        })
      if (url.pathname.endsWith("/deliveries")) {
        if (current === 2 && failDeliveries)
          return route.fulfill({
            status: 500,
            json: { error: { code: "unavailable", message: "投递记录暂不可用" } },
          })
        return route.fulfill({
          json: {
            data: {
              items: [
                {
                  id: `d${current}`,
                  created_at: "2026-10-23T01:00:00Z",
                  channel: "ntfy",
                  status: current === 1 ? "delivered" : "retry",
                  attempts: current,
                  error_code: current === 2 ? "ntfy_transport" : undefined,
                },
              ],
              page: current,
              page_size: 10,
              total: 11,
            },
          },
        })
      }
      return route.fulfill({ json: { data: { ...item, destination: "fixture-topic" } } })
    })
    await page.goto("/notifications")
    await page.getByRole("button", { name: "编辑渠道 停用提醒" }).click()
    const dialog = page.getByRole("dialog", { name: "编辑通知渠道" })
    await expect(dialog.getByLabel("通知目标", { exact: true })).toHaveValue("fixture-topic")
    await expect(dialog.getByLabel("通知目标", { exact: true })).toHaveAttribute("type", "password")
    await dialog.getByRole("button", { name: "显示通知目标", exact: true }).click()
    await expect(dialog.getByLabel("通知目标", { exact: true })).toHaveAttribute("type", "text")
    await dialog.getByLabel("渠道名称").fill("改名后的停用提醒")
    await dialog.getByLabel("通知目标", { exact: true }).fill("edited-fixture-topic")
    await dialog.getByRole("button", { name: "保存渠道", exact: true }).click()
    await expect(dialog.getByRole("alert")).toContainText("保存暂时失败")
    await expect(dialog.getByLabel("通知目标", { exact: true })).toHaveValue("edited-fixture-topic")
    await dialog.getByRole("button", { name: "保存渠道", exact: true }).click()
    await expect(dialog).toHaveCount(0)
    expect(saved).toMatchObject({
      enabled: false,
      destination: "edited-fixture-topic",
      name: "改名后的停用提醒",
    })
    await expect(page.getByRole("table", { name: "已配置渠道", exact: true })).toContainText(
      "改名后的停用提醒",
    )
    await page.getByRole("button", { name: "显示通知目标 改名后的停用提醒" }).click()
    await expect(page.getByText("fixture-topic", { exact: true })).toBeVisible()
    await page.getByRole("button", { name: "隐藏通知目标 改名后的停用提醒" }).click()
    await expect(page.getByText("fixture-topic", { exact: true })).toHaveCount(0)
    await page
      .getByRole("navigation", { name: "通知渠道分页" })
      .getByRole("button", { name: "下一页" })
      .click()
    await expect(page.getByRole("table", { name: "已配置渠道", exact: true })).toContainText(
      "第二页渠道",
    )
    await page
      .getByRole("navigation", { name: "投递记录分页" })
      .getByRole("button", { name: "下一页" })
      .click()
    await expect(page.getByRole("alert")).toContainText("投递记录暂不可用")
    failDeliveries = false
    await page.getByRole("button", { name: "重试投递列表" }).click()
    await expect(page.getByRole("table", { name: "最近投递", exact: true })).toContainText(
      "ntfy_transport",
    )
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    )
    await page.screenshot({
      path: testInfo.outputPath(`notifications-${width}.png`),
      fullPage: true,
    })
  })
}

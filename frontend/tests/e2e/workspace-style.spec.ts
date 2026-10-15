import { expect, type Page, test } from "@playwright/test"

import type { Backtest } from "../../src/features/backtests/api"

// v1: 固定离线界面 fixture，只供展示与响应式回归使用。
const run: Backtest = {
  id: "backtest-ui-v1",
  strategy_version_id: "双均线策略-v3",
  status: "succeeded",
  progress: 100,
  snapshot_id: "snapshot-ui-v1",
  application_version: "fixture-v1",
  metrics: {
    cumulative_return: "0.1842",
    annualized_return: "0.1721",
    max_drawdown: "0.0638",
    trade_count: 42,
  },
  periods: [
    { trading_day: "2026-01-05", equity: "100000" },
    { trading_day: "2026-02-02", equity: "104200" },
    { trading_day: "2026-03-02", equity: "102900" },
    { trading_day: "2026-04-01", equity: "110600" },
    { trading_day: "2026-05-06", equity: "108100" },
    { trading_day: "2026-06-01", equity: "118420" },
  ],
  trades: [
    {
      trading_day: "2026-01-05",
      symbol: "000001",
      action: "buy",
      quantity: "100",
      price: "10.50",
      fee: "5.00",
    },
  ],
  assumptions: { fee_rate: "0.0003", slippage_rate: "0.001" },
}

async function mockWorkspace(page: Page, role: "admin" | "user" = "admin") {
  await page.route("**/api/v1/**", (route) => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "")
    const responses: Record<string, unknown> = {
      "/auth/me": { user: { id: "ui-user", username: "研究员", role, status: "active" } },
      "/strategies": [
        {
          id: "strategy-ui",
          name: "双均线策略",
          description: "离线界面示例",
          current_version_id: "version-ui",
          versions: [],
        },
      ],
      "/strategies/templates": [],
      "/backtests": [run, { ...run, id: "backtest-queued", status: "queued", metrics: {} }],
      [`/backtests/${run.id}`]: run,
      "/live-instances": [],
    }
    if (!(path in responses))
      return route.fulfill({
        status: 404,
        json: { error: { code: "fixture_missing", message: `未定义界面 fixture: ${path}` } },
      })
    return route.fulfill({ json: { data: responses[path] } })
  })
}

async function expectNoPageOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  )
}

test("桌面概览与回测详情显示真实 fixture，导航定位与图表清晰", async ({ page }, testInfo) => {
  await mockWorkspace(page)
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto("/")
  await expect(page.getByRole("heading", { name: "研究概览" })).toBeVisible()
  await expect(page.getByRole("region", { name: "回测记录", exact: true })).toContainText("2")
  await expect(page.locator('a[aria-current="page"]')).toHaveCount(1)
  await expectNoPageOverflow(page)
  await page.screenshot({ path: testInfo.outputPath("tremor-overview.png"), fullPage: true })
  await page.getByRole("link", { name: run.id, exact: true }).click()
  await expect(page.getByRole("heading", { name: "回测详情" })).toBeVisible()
  await expect(page.getByRole("link", { name: "回测", exact: true })).toHaveAttribute(
    "aria-current",
    "page",
  )
  await expect(page.getByRole("region", { name: "累计收益率" })).toContainText("18.42%")
  await expect(page.getByRole("img", { name: /组合权益曲线/ })).toBeVisible()
  await expect(page.locator(".recharts-area-curve")).toHaveAttribute("d", /M.+/)
  await expectNoPageOverflow(page)
  await page.screenshot({ path: testInfo.outputPath("tremor-backtest.png"), fullPage: true })
  await page.getByRole("button", { name: "切换导航" }).click()
  await expect(page.locator('[data-slot="sidebar"]').first()).toHaveAttribute(
    "data-state",
    "collapsed",
  )
})

test("360px 普通用户可打开导航、切换页面且无管理入口或页面溢出", async ({ page }, testInfo) => {
  await mockWorkspace(page, "user")
  await page.setViewportSize({ width: 360, height: 900 })
  await page.goto("/")
  await expect(page.getByRole("heading", { name: "研究概览" })).toBeVisible()
  await expectNoPageOverflow(page)
  await page.getByRole("button", { name: "切换导航" }).click()
  const menu = page.getByRole("dialog")
  await expect(menu).toBeVisible()
  await expect(menu.getByRole("link", { name: "数据管理" })).toHaveCount(0)
  await expect(menu.getByRole("link", { name: "系统管理" })).toHaveCount(0)
  await menu.getByRole("link", { name: "回测", exact: true }).click()
  await expect(menu).not.toBeVisible()
  await expect(page.getByRole("heading", { name: "回测研究" })).toBeVisible()
  await expectNoPageOverflow(page)
  await page.getByRole("link", { name: run.id, exact: true }).click()
  await expect(page.getByRole("heading", { name: "回测详情" })).toBeVisible()
  await expectNoPageOverflow(page)
  await page.screenshot({ path: testInfo.outputPath("tremor-mobile.png"), fullPage: true })
})

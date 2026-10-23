import { expect, type Page, test } from "@playwright/test"

import type { Backtest } from "../../src/features/backtests/api"

// v1: 固定离线界面 fixture，只供展示与响应式回归使用。
const run: Backtest = {
  id: "backtest-ui-v1",
  strategy_version_id: "双均线策略-v3",
  strategy: {
    id: "strategy-ui",
    name: "双均线策略",
    description: "离线界面示例",
    version_id: "version-ui",
    number: 3,
    source_code: `# ${"historical-source-".repeat(40)}`,
  },
  benchmark: { symbol: "sh000300", name: "沪深300" },
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
    { trading_day: "2026-01-05", equity: "100000", benchmark_equity: "100000" },
    { trading_day: "2026-02-02", equity: "104200", benchmark_equity: "102000" },
    { trading_day: "2026-03-02", equity: "102900", benchmark_equity: "101000" },
    { trading_day: "2026-04-01", equity: "110600", benchmark_equity: "106000" },
    { trading_day: "2026-05-06", equity: "108100", benchmark_equity: "105000" },
    { trading_day: "2026-06-01", equity: "118420", benchmark_equity: "110000" },
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
      "/strategies/workspace": { items: [], total: 0, page: 1, page_size: 20 },
      "/backtests": [run, { ...run, id: "backtest-queued", status: "queued", metrics: {} }],
      [`/backtests/${run.id}`]: run,
      "/live-instances": [],
    }
    if (!(path in responses))
      return route.fulfill({
        status: 404,
        json: { error: { code: "fixture_missing", message: `未定义界面 fixture: ${path}` } },
      })
    return route.fulfill({
      json: {
        data:
          path === "/live-instances" && new URL(route.request().url()).searchParams.has("page")
            ? { items: [], total: 0, page: 1, page_size: 20 }
            : responses[path],
      },
    })
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
  await expect(page.locator(".recharts-line-curve")).toHaveAttribute("stroke", "var(--chart-2)")
  await expect(page.locator(".recharts-line-curve")).toHaveAttribute("d", /M.+L.+/)
  await expectNoPageOverflow(page)
  await page.screenshot({ path: testInfo.outputPath("tremor-backtest.png"), fullPage: true })
  await page.getByRole("button", { name: "收起侧栏" }).click()
  await expect(page.locator('[data-slot="sidebar"]').first()).toHaveAttribute(
    "data-state",
    "collapsed",
  )
})

test("桌面侧栏顶部控制展开收起，悬停与键盘可发现展开入口", async ({ page }, testInfo) => {
  await mockWorkspace(page)
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto("/")
  const sidebar = page.locator('[data-slot="sidebar"]').first()
  const header = page.locator('[data-slot="sidebar-header"]')
  const collapse = header.getByRole("button", { name: "收起侧栏", exact: true })
  await expect(collapse).toHaveAttribute("aria-expanded", "true")
  await expect(page.getByRole("button", { name: "切换导航", exact: true })).toHaveCount(0)
  const controlBox = await collapse.boundingBox()
  const sidebarBox = await page.locator('[data-slot="sidebar-container"]').boundingBox()
  expect(controlBox!.x + controlBox!.width).toBeLessThanOrEqual(sidebarBox!.width)
  await page.screenshot({
    path: testInfo.outputPath("sidebar-expanded.png"),
    clip: { x: 0, y: 0, width: 560, height: 560 },
  })
  await collapse.click()
  await expect(sidebar).toHaveAttribute("data-state", "collapsed")
  await expect
    .poll(async () => (await page.locator('[data-slot="sidebar-container"]').boundingBox())!.width)
    .toBe(48)
  const expand = header.getByRole("button", { name: "展开侧栏", exact: true })
  await expect(expand).toHaveAttribute("aria-expanded", "false")
  await page.mouse.move(600, 300)
  await expect(expand.locator('[data-slot="sidebar-brand-icon"]')).toHaveCSS("opacity", "1")
  await expect(expand.locator('[data-slot="sidebar-expand-icon"]')).toHaveCSS("opacity", "0")
  await expand.hover()
  await expect(page.getByRole("tooltip", { name: "展开", exact: true })).toBeVisible()
  await expect(expand.locator('[data-slot="sidebar-expand-icon"]')).toHaveCSS("opacity", "1")
  await expect(sidebar).toHaveAttribute("data-state", "collapsed")
  await page.screenshot({
    path: testInfo.outputPath("sidebar-collapsed-hover.png"),
    clip: { x: 0, y: 0, width: 560, height: 560 },
  })
  await expand.click()
  await expect(sidebar).toHaveAttribute("data-state", "expanded")
  await expect(collapse).toBeFocused()
  await collapse.press("Enter")
  await page.mouse.move(600, 300)
  await page.keyboard.press("Tab")
  await page.keyboard.press("Shift+Tab")
  await expect(expand).toBeFocused()
  await expect(expand.locator('[data-slot="sidebar-expand-icon"]')).toHaveCSS("opacity", "1")
  await expect(page.getByRole("tooltip", { name: "展开", exact: true })).toBeVisible()
  await expand.press("Space")
  await expect(sidebar).toHaveAttribute("data-state", "expanded")
  await page.keyboard.press("Control+b")
  await expect(sidebar).toHaveAttribute("data-state", "collapsed")
  await page.getByRole("link", { name: "回测", exact: true }).click()
  await expect(page.getByRole("heading", { name: "回测研究" })).toBeVisible()
  await expect(sidebar).toHaveAttribute("data-state", "collapsed")
  await expectNoPageOverflow(page)
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
  await expect(menu.getByRole("link", { name: "指数数据" })).toHaveCount(0)
  await menu.getByRole("link", { name: "回测", exact: true }).click()
  await expect(menu).not.toBeVisible()
  await expect(page.getByRole("heading", { name: "回测研究" })).toBeVisible()
  await expectNoPageOverflow(page)
  await page.getByRole("link", { name: run.id, exact: true }).click()
  await expect(page.getByRole("heading", { name: "回测详情" })).toBeVisible()
  await expectNoPageOverflow(page)
  await page.getByText("预览策略代码", { exact: true }).click()
  await expectNoPageOverflow(page)
  await page.screenshot({ path: testInfo.outputPath("tremor-mobile.png"), fullPage: true })
})

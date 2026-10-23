import { expect, type Page, test } from "@playwright/test"

// v1：固定 UI 压力 fixture，只用于本地内存环境，不提交线上业务数据。
const longId = "ui-fixture-v1-" + "long-identifier-".repeat(7)
const live = {
  id: longId,
  backtest_id: "backtest-audit-v1",
  strategy_version_id: longId,
  status: "active",
  next_decision_at: "2026-09-30T01:00:00Z",
  recommendations: [1, 2].map((index) => ({
    id: `recommendation-audit-v1-${index}`,
    instrument_id: "000001",
    action: "buy",
    quantity: "100",
    reason: longId,
    status: "pending",
    version: 1,
  })),
}
const strategy = {
  id: "strategy-audit-v1",
  version_id: "version-audit-v1",
  number: 1,
  name: "界面压力策略",
  description: longId,
  state: "draft",
  created_at: "2026-09-30T01:00:00Z",
  revision: 0,
  live_instances: [],
  source_code:
    "def before_market(context, parameters):\n    return []\n\ndef on_market(context, parameters):\n    return []\n\ndef after_market(context, parameters):\n    return []\n",
}
const backtest = {
  id: "backtest-audit-v1",
  strategy_version_id: longId,
  status: "succeeded",
  progress: 100,
  snapshot_id: longId,
  application_version: "ui-audit-v1",
  metrics: { cumulative_return: "0.1" },
  periods: [{ trading_day: "2026-09-30", equity: "100000" }],
  trades: [],
  assumptions: {},
}

async function prepare(page: Page) {
  await page.goto("/login")
  await page.getByLabel("用户名", { exact: true }).fill("admin")
  await page.getByLabel("密码", { exact: true }).fill("change-this-admin-password")
  await page.getByRole("button", { name: "登录", exact: true }).click()
  await expect(page).toHaveURL(/\/$/)
  const fixtures: Record<string, unknown> = {
    "/auth/me": {
      user: { id: "audit-admin-v1", username: longId, role: "admin", status: "active" },
    },
    "/strategies/workspace": { items: [strategy], page: 1, page_size: 20, total: 1 },
    "/strategies/strategy-audit-v1/versions/version-audit-v1": strategy,
    "/strategies": [
      {
        id: strategy.id,
        name: strategy.name,
        description: strategy.description,
        current_version_id: strategy.version_id,
        versions: [{ ...strategy, id: strategy.version_id }],
      },
    ],
    "/backtests": [backtest],
    "/backtests/backtest-audit-v1": backtest,
    "/backtests/backtest-audit-v1/stock-performance": {
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
    },
    "/live-instances": [live],
    [`/live-instances/${longId}`]: live,
    "/admin/market-data/instruments/000001": {
      symbol: "000001",
      name: "平安银行",
      exchange: "SZSE",
      status: "active",
      listed_on: "1991-04-03",
    },
    "/admin/market-data/instruments/000001/daily-bars": [],
    "/notifications/subscriptions": [
      { id: "subscription-audit-v1", channel: "ntfy", destination: longId, enabled: true },
    ],
    [`/live-instances/${longId}/portfolio`]: {
      cash: "100000",
      available_cash: "100000",
      reserved_cash: "0",
      positions: {},
      reserved_positions: {},
      capital_pool: "100000",
      profit: null,
      return_rate: null,
      missing_symbols: [],
      curve: [],
      valuation_note: "暂无估值",
    },
    [`/live-instances/${longId}/deliveries`]: { items: [], total: 0, page: 1, page_size: 20 },
    "/admin/invitations": [{ id: longId, expires_at: "2026-10-07T00:00:00Z" }],
  }
  await page.route("**/api/v1/**", (route) => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "")
    if (route.request().method() === "GET" && path in fixtures)
      return route.fulfill({
        json: {
          data:
            ["/notifications/subscriptions", "/live-instances"].includes(path) &&
            new URL(route.request().url()).searchParams.has("page")
              ? {
                  items: fixtures[path],
                  total: 1,
                  page: 1,
                  page_size: path === "/live-instances" ? 20 : 10,
                }
              : fixtures[path],
        },
      })
    return route.continue()
  })
}

const routes = [
  ["/", "研究概览"],
  ["/strategies", "策略工作台"],
  ["/factors", "因子目录"],
  ["/strategy-library", "新建策略"],
  ["/strategies/new", "新建策略"],
  ["/strategies/strategy-audit-v1/versions/version-audit-v1", "界面压力策略 · v1"],
  ["/strategies/strategy-audit-v1/versions/version-audit-v1/edit", "编辑 界面压力策略 · v1"],
  ["/backtests", "回测研究"],
  ["/backtests/new", "创建回测"],
  ["/backtests/backtest-audit-v1", "回测详情"],
  ["/live", "实盘建议跟踪"],
  [`/live/${longId}`, `实盘实例 ${longId}`],
  ["/notifications", "通知设置"],
  ["/admin", "系统管理"],
  ["/admin/data", "数据管理"],
  ["/admin/data?tab=indices", "同步指数历史日线"],
  ["/admin/data/indices", "同步指数历史日线"],
  ["/admin/data/acquisitions", "刷新基础数据"],
  ["/admin/data/import", "上传行情数据"],
  ["/admin/data/instruments/000001", "000001 平安银行"],
  ["/admin/users", "用户管理"],
  ["/admin/invitations", "签发邀请码"],
  ["/admin/schedules", "定时任务"],
  ["/admin/jobs", "后台任务"],
  ["/admin/audit", "审计记录"],
] as const

for (const width of [360, 768, 1440]) {
  test(`${width}px 全部页面与兼容入口的布局、长文本及表单标签`, async ({ page }, testInfo) => {
    test.setTimeout(90000)
    await page.setViewportSize({ width, height: 1000 })
    await prepare(page)
    for (const [path, title] of routes) {
      await page.goto(path)
      await expect(page.getByText(title, { exact: true }).last()).toBeVisible()
      await expect(page.getByRole("alertdialog")).toHaveCount(0)
      await expect(page.locator('[role="status"][aria-label^="正在加载"]')).toHaveCount(0)
      await expect(page.getByText("正在统计数据覆盖…", { exact: true })).toHaveCount(0)
      const layout = await page.evaluate(() => ({
        width: window.innerWidth,
        scroll: document.documentElement.scrollWidth,
        duplicateIds: [...document.querySelectorAll("[id]")]
          .map((node) => node.id)
          .filter((id, index, all) => all.indexOf(id) !== index),
      }))
      expect.soft(layout.scroll, `${path} 页面横向溢出`).toBeLessThanOrEqual(layout.width)
      expect.soft(layout.duplicateIds, `${path} 重复 ID`).toEqual([])
      if (path === "/admin/data") {
        expect(
          (await page.getByRole("heading", { name: title }).boundingBox())!.width,
        ).toBeGreaterThan(180)
        await page.screenshot({ path: testInfo.outputPath(`data-${width}.png`), fullPage: true })
      }
      if (path === "/backtests/new")
        await expect(page.getByRole("combobox", { name: "策略版本" })).toBeVisible()
      if (path === "/notifications") {
        await page.getByRole("button", { name: "添加渠道", exact: true }).click()
        await expect(page.getByRole("dialog", { name: "添加通知渠道" })).toBeVisible()
        await expect(page.getByRole("combobox", { name: "渠道" })).toBeVisible()
        await page.getByRole("button", { name: "取消", exact: true }).click()
        await expect(page.getByRole("dialog")).toHaveCount(0)
      }
      if (path === `/live/${longId}`) {
        for (const button of await page
          .getByRole("button", { name: "修正成交", exact: true })
          .all()) {
          await button.click()
          await expect(page.getByRole("dialog", { name: "修正成交" })).toBeVisible()
          await expect(page.getByRole("combobox", { name: "实际方向" })).toHaveCount(0)
          await expect(page.getByLabel("实际数量")).toHaveValue("100")
          await page.getByRole("button", { name: "关闭", exact: true }).click()
        }
        const ids = await page
          .locator("input[id]")
          .evaluateAll((nodes) => nodes.map((node) => node.id))
        expect(new Set(ids).size).toBe(ids.length)
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
          width,
        )
      }
    }
    if (width === 360) {
      await page.getByRole("button", { name: "切换导航" }).click()
      await expect(page.getByRole("dialog")).toBeVisible()
      await page.getByRole("button", { name: "关闭面板" }).click()
      await expect(page.getByRole("dialog")).toHaveCount(0)
    } else {
      await expect(page.getByRole("button", { name: "退出登录", exact: true })).toBeVisible()
    }
    for (const [path, title] of [
      ["/login", "登录 Easy Quant 易量化平台"],
      ["/register", "使用邀请码注册"],
    ]) {
      await page.goto(path)
      await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
        width,
      )
    }
  })
}

test("因子无搜索结果与实盘空态、加载失败后可恢复", async ({ page }) => {
  await prepare(page)
  await page.goto("/factors")
  await page.getByLabel("搜索因子").fill("no-such-factor-ui-v1")
  await expect(page.getByText("没有匹配的因子", { exact: true })).toBeVisible()
  let failed = true
  await page.route("**/api/v1/live-instances/retry-ui-v1?view=summary", (route) =>
    failed
      ? route.fulfill({
          status: 503,
          json: { error: { code: "unavailable", message: "暂时无法读取实例" } },
        })
      : route.fulfill({ json: { data: { ...live, id: "retry-ui-v1", recommendations: [] } } }),
  )
  await page.goto("/live/retry-ui-v1")
  await expect(page.getByRole("alert")).toContainText("无法加载实盘实例")
  failed = false
  await page.getByRole("button", { name: "重新加载", exact: true }).click()
  await expect(page.getByRole("heading", { name: "实盘实例 retry-ui-v1" })).toBeVisible()
  await expect(page.getByText("暂无操作", { exact: true })).toBeVisible()
})

test("保存失败提供明确反馈，CSV 切换数据集后重新预检", async ({ page }) => {
  await prepare(page)
  const pageErrors: string[] = []
  page.on("pageerror", (error) => pageErrors.push(error.message))
  await page.route("**/api/v1/**", (route) => {
    if (route.request().method() === "GET") return route.fallback()
    return route.fulfill({
      status: 503,
      json: { error: { code: "unavailable", message: "服务暂不可用，请稍后重试" } },
    })
  })
  await page.goto("/admin/data")
  await page.getByRole("button", { name: "东方财富 已启用", exact: true }).first().click()
  await expect(page.getByRole("alert")).toContainText("保存失败，已恢复原配置")
  await page.goto("/notifications")
  await page.getByRole("button", { name: "添加渠道", exact: true }).click()
  await page.getByLabel("渠道名称", { exact: true }).fill("UI 压力渠道")
  await page.getByLabel("通知目标", { exact: true }).fill("ui-fixture-v1")
  await page.getByRole("dialog").getByRole("button", { name: "添加渠道", exact: true }).click()
  await expect(page.getByRole("alert")).toContainText("服务暂不可用")
  await expect(page.getByLabel("通知目标", { exact: true })).toHaveValue("ui-fixture-v1")
  await page.goto("/admin/invitations")
  await page.getByRole("button", { name: "签发邀请码", exact: true }).click()
  await expect(page.getByRole("alert")).toContainText("无法签发邀请码")
  await page.goto("/backtests/backtest-audit-v1")
  await page.getByRole("button", { name: "开启实盘跟踪", exact: true }).click()
  await page.getByLabel("实盘名称", { exact: true }).fill("界面测试实盘")
  await page.getByLabel("实盘初始资金", { exact: true }).fill("100000")
  await page.getByRole("checkbox", { name: "ntfy", exact: true }).check()
  await page.getByRole("button", { name: "确认启动实盘", exact: true }).click()
  await expect(page.getByRole("alert")).toContainText("服务暂不可用")
  await page.goto("/admin/data/import")
  const file = {
    name: "ui-v1.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "symbol,trading_day,open,high,low,close,volume\n000001,2026-09-30,10,11,9,10.5,1000",
    ),
  }
  await page.getByLabel("选择 CSV 文件").setInputFiles(file)
  await expect(page.getByRole("alert")).toContainText("文件导入未完成")
  await expect(page.getByRole("button", { name: "确认导入" })).toBeDisabled()
  await page.route("**/api/v1/admin/market-data/imports/preview", (route) =>
    route.fulfill({
      json: { data: { valid: true, rows: 1, issues: [], preview_id: "preview-ui-v1" } },
    }),
  )
  await page.getByLabel("选择 CSV 文件").setInputFiles(file)
  await expect(page.getByRole("button", { name: "确认导入" })).toBeEnabled()
  await page.getByRole("combobox", { name: "导入数据集" }).click()
  await page.getByRole("option", { name: "估值与市值", exact: true }).click()
  await expect(page.getByRole("button", { name: "确认导入" })).toBeDisabled()
  expect(pageErrors).toEqual([])
})

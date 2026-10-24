import { expect, test } from "@playwright/test"

const source =
  "def before_market(context, parameters):\n    return []\n\ndef on_market(context, parameters):\n    return []\n\ndef after_market(context, parameters):\n    return []\n"

test("策略版本分页、草稿编辑、锁定复制、模板确认与公共库侧栏", async ({ page }, testInfo) => {
  test.setTimeout(60000)
  await page.goto("/login")
  await page.getByLabel("用户名").fill("admin")
  await page.getByLabel("密码").fill("change-this-admin-password")
  await page.getByRole("button", { name: "登录", exact: true }).click()
  await expect(page).toHaveURL(/\/$/)
  const session = (await (await page.request.get("/api/v1/auth/me")).json()).data
  const headers = { "X-CSRF-Token": session.csrf_token }
  const created = await page.request.post("/api/v1/strategies", {
    headers,
    data: { name: "workspace-pagination-v1", source_code: source },
  })
  expect(created.ok()).toBeTruthy()
  const strategy = (await created.json()).data
  const id = strategy.id
  const first = strategy.current_version_id
  for (let index = 0; index < 20; index += 1) {
    const added = await page.request.post(`/api/v1/strategies/${id}/versions`, {
      headers,
      data: { source_code: source },
    })
    expect(added.ok()).toBeTruthy()
  }
  await page.goto("/strategies?search=workspace-pagination-v1")
  await expect(page.getByRole("heading", { name: "策略工作台" })).toBeVisible()
  await expect(page.getByLabel("策略代码编辑器")).toHaveCount(0)
  await expect(page.getByRole("table").locator("tbody tr")).toHaveCount(20)
  await page.getByRole("link", { name: "下一页" }).click()
  await expect(page.getByRole("table").locator("tbody tr")).toHaveCount(1)
  await expect(page.getByText(/第 2 \/ 2 页/)).toBeVisible()
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.screenshot({ path: testInfo.outputPath("strategy-list-desktop.png"), fullPage: true })

  const submitted = await page.request.post("/api/v1/backtests", {
    headers,
    data: {
      strategy_version_id: first,
      start_day: "2026-09-28",
      end_day: "2026-09-29",
      initial_cash: "100000",
    },
  })
  expect(submitted.status()).toBe(202)
  await page.goto(`/strategies/${id}/versions/${first}`)
  await expect(page.getByText("测试中", { exact: true })).toBeVisible()
  await page.getByRole("button", { name: "编辑 workspace-pagination-v1 v1" }).click()
  await expect(page.getByRole("alertdialog")).toContainText("原策略代码、回测及实盘引用保持不变")
  await page.getByRole("button", { name: "取消" }).click()
  await expect(page.getByLabel("策略代码编辑器")).toHaveCount(0)
  await page.getByRole("button", { name: "编辑 workspace-pagination-v1 v1" }).click()
  await page.getByRole("button", { name: "确认创建草稿版本" }).click()
  await expect(page).toHaveURL(/\/versions\/[^/]+\/edit$/)
  await expect(page.getByLabel("策略代码编辑器")).toBeVisible()
  const editUrl = page.url()
  await page.getByLabel("名称", { exact: true }).fill("独立草稿")
  await page.getByRole("button", { name: "保存草稿" }).click()
  await expect(page.getByText("草稿已保存", { exact: true })).toBeVisible()
  const original = (
    await (await page.request.get(`/api/v1/strategies/${id}/versions/${first}`)).json()
  ).data
  expect(original.source_code).toBe(source)
  expect(original.state).toBe("testing")

  await page.getByRole("button", { name: "代码模板" }).click()
  await page.getByRole("menuitem", { name: "使用5 日均线选股" }).click()
  await page.getByRole("button", { name: "取消" }).click()
  await expect(page.locator(".monaco-editor .view-lines")).not.toContainText("market.daily-bars")
  await page.getByRole("button", { name: "代码模板" }).click()
  await page.getByRole("menuitem", { name: "使用5 日均线选股" }).click()
  await page.getByRole("button", { name: "确认替换模板" }).click()
  await expect(page.locator(".monaco-editor .view-lines")).toContainText("market.daily-bars")
  const sidebar = page.getByRole("complementary", { name: "策略公共库" })
  const triggers = sidebar.locator('[data-slot="accordion-trigger"]')
  await expect(triggers.first()).toHaveAttribute("aria-expanded", "false")
  await triggers.first().click()
  await expect(triggers.first()).toHaveAttribute("aria-expanded", "true")
  const before = await sidebar.getByLabel("搜索库函数").boundingBox()
  await sidebar.locator('[data-slot="card-content"]').evaluate((element) => {
    element.scrollTop = element.scrollHeight
  })
  const after = await sidebar.getByLabel("搜索库函数").boundingBox()
  expect(after?.y).toBe(before?.y)
  async function expectQuickTestAlignment() {
    const calendar = await page
      .getByRole("button", { name: "选择日期 strategy-run-day", exact: true })
      .boundingBox()
    const run = await page.getByRole("button", { name: "运行快速测试", exact: true }).boundingBox()
    expect(calendar).not.toBeNull()
    expect(run).not.toBeNull()
    expect(Math.abs(run!.y + run!.height / 2 - (calendar!.y + calendar!.height / 2))).toBeLessThan(
      1,
    )
    expect(run!.x).toBeGreaterThanOrEqual(calendar!.x + calendar!.width)
  }
  await expectQuickTestAlignment()
  await page.screenshot({
    path: testInfo.outputPath("strategy-editor-library-desktop.png"),
    fullPage: true,
  })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  )
  await sidebar.getByLabel("搜索库函数").fill("context.position")
  await expect(triggers).toHaveCount(1)

  await page.setViewportSize({ width: 360, height: 900 })
  await page.goto(editUrl)
  await expect(page.getByLabel("策略代码编辑器")).toBeVisible()
  await expect(page.getByRole("complementary", { name: "策略公共库" })).toBeAttached()
  await expectQuickTestAlignment()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  )
  await page.screenshot({ path: testInfo.outputPath("strategy-editor-360.png"), fullPage: true })
})

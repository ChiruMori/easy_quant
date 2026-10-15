import { expect, type Page, test } from "@playwright/test"

async function loginAsAdmin(page: Page) {
  await page.goto("/login")
  await page.getByLabel("用户名").fill("admin")
  await page.getByLabel("密码").fill("change-this-admin-password")
  await page.getByRole("button", { name: "登录", exact: true }).click()
  await expect(page).toHaveURL(/\/$/)
}

test("管理员登录、数据管理、任务管理与邀请注册主旅程", async ({ page }, testInfo) => {
  await loginAsAdmin(page)
  await expect(page.getByRole("heading", { name: "Easy Quant 易量化平台" })).toBeVisible()
  const sidebar = page.locator('[data-slot="sidebar-container"]')
  await expect(sidebar).toBeVisible()
  await expect.poll(async () => (await sidebar.boundingBox())?.width ?? 0).toBeGreaterThan(200)
  const background = await page
    .locator("body")
    .evaluate((node) => getComputedStyle(node).backgroundColor)
  expect(background).not.toBe("rgba(0, 0, 0, 0)")

  await page.goto("/admin/data")
  await expect(page.getByText("日线 K 线")).toBeVisible()
  await expect(page.getByText("AKShare").first()).toBeVisible()
  await page.getByRole("link", { name: "整体同步（推荐）" }).click()
  await expect(page).toHaveURL(/\/admin\/schedules$/)
  await expect(page.getByRole("heading", { name: "定时任务", exact: true })).toBeVisible()
  await expect(page.getByRole("combobox", { name: "任务类型" })).toHaveText("盘后全量数据同步")
  await page.goto("/admin/data")
  await page.getByRole("link", { name: "上传 CSV" }).click()
  await page.getByLabel("选择 CSV 文件").setInputFiles({
    name: "daily-bars.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "symbol,trading_day,open,high,low,close,volume\n000001,2026-09-30,10,11,9,10.5,1000",
    ),
  })
  await expect(page.getByText(/预检通过/)).toBeVisible()
  await page.getByRole("button", { name: "确认导入" }).click()
  await expect(page.getByText(/已导入/)).toBeVisible()

  await page.goto("/admin/schedules")
  let releaseWrite!: () => void
  let posts = 0
  const writeGate = new Promise<void>((resolve) => {
    releaseWrite = resolve
  })
  await page.route("**/api/v1/admin/schedules", async (route) => {
    if (route.request().method() === "POST") {
      posts += 1
      await writeGate
    }
    await route.continue()
  })
  await page.getByRole("button", { name: "创建任务" }).click()
  const loading = page.getByRole("alertdialog", { name: "正在处理，请稍候" })
  await expect(loading).toBeVisible()
  await loading.press("Escape")
  await expect(loading).toBeVisible()
  expect(posts).toBe(1)
  releaseWrite()
  await expect(page.getByRole("cell", { name: "0 22 * * 1-5" })).toBeVisible()
  await expect(loading).toHaveCount(0)
  await page.unroute("**/api/v1/admin/schedules")
  await expect(page.getByRole("cell", { name: "盘后全量数据同步" })).toBeVisible()
  const nightly = page
    .getByRole("row")
    .filter({ has: page.getByRole("cell", { name: "盘后全量数据同步" }) })
  await expect(nightly.getByRole("button", { name: "编辑" })).toBeDisabled()
  await nightly.getByRole("switch").click()
  await nightly.getByRole("button", { name: "编辑" }).click()
  await page.getByLabel("Cron 表达式").fill("0 21 * * 1-5")
  await page.getByRole("button", { name: "保存计划" }).click()
  await expect(nightly.getByRole("cell", { name: "0 21 * * 1-5" })).toBeVisible()
  await nightly.getByRole("button", { name: "立即执行" }).click()
  await expect(page.getByText(/已进入队列，可在后台任务页面查看结果/)).toBeVisible()
  await page.getByRole("combobox", { name: "任务类型" }).click()
  await page.getByRole("option", { name: "通达信 A 股盘后增量" }).click()
  await page.getByRole("button", { name: "创建任务" }).click()
  await expect(page.getByRole("cell", { name: "通达信 A 股盘后增量" })).toBeVisible()

  await page.goto("/admin/invitations")
  await page.getByRole("button", { name: "签发邀请码" }).click()
  const token = await page.locator(".font-mono").textContent()
  expect(token).toBeTruthy()
  await page.getByRole("button", { name: /退出登录/ }).click()
  await page.getByRole("link", { name: "使用邀请码注册" }).click()
  const username = `invitee-${Date.now()}`
  await page.getByLabel("邀请码").fill(token ?? "")
  await page.getByLabel("用户名").fill(username)
  await page.getByLabel("密码").fill("invited-user-password")
  await page.getByRole("button", { name: "创建账号" }).click()
  await expect(page).toHaveURL(/\/login$/)
  await page.getByLabel("用户名").fill(username)
  await page.getByLabel("密码").fill("invited-user-password")
  await page.getByRole("button", { name: "登录", exact: true }).click()
  await expect(page.getByRole("heading", { name: "Easy Quant 易量化平台" })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath("styled-dashboard.png"), fullPage: true })
})

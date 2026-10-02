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
  await page.getByRole("button", { name: "创建任务" }).click()
  await expect(page.getByRole("cell", { name: "0 18 * * 1-5" })).toBeVisible()
  await page.getByRole("combobox").click()
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

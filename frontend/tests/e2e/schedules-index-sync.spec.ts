import { expect, test } from "@playwright/test"

test("默认停用的指数计划可编辑并手动同步，重复用途说明清晰", async ({ page }, testInfo) => {
  await page.goto("/login")
  await page.getByLabel("用户名").fill("admin")
  await page.getByLabel("密码").fill("change-this-admin-password")
  await page.getByRole("button", { name: "登录", exact: true }).click()
  await expect(page).toHaveURL(/\/$/)
  await page.goto("/admin/schedules")
  const index = page
    .getByRole("row")
    .filter({ has: page.getByRole("cell", { name: "主要指数日线同步", exact: true }) })
  await expect(index.getByRole("switch")).not.toBeChecked()
  await index.getByRole("button", { name: "编辑", exact: true }).click()
  await expect(page.getByText(/补齐七个主要指数至最近已发布交易日/)).toBeVisible()
  await page
    .getByLabel("任务配置 JSON")
    .fill(JSON.stringify({ symbols: ["sh000016"], start_day: "2026-09-28", end_day: "2026-09-29" }))
  await page.getByRole("button", { name: "保存计划" }).click()
  await index.getByRole("button", { name: "立即执行" }).click()
  await expect(page.getByText(/已进入队列，可在后台任务页面查看结果/)).toBeVisible()
  await expect(index.getByRole("switch")).not.toBeChecked()
  await page.screenshot({ path: testInfo.outputPath("index-schedule-desktop.png"), fullPage: true })
  await page.setViewportSize({ width: 360, height: 900 })
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    .toBeTruthy()
  await page.screenshot({ path: testInfo.outputPath("index-schedule-mobile.png"), fullPage: true })
  await page.goto("/admin/jobs")
  const job = page
    .getByRole("row")
    .filter({ has: page.getByRole("cell", { name: "主要指数日线同步", exact: true }) })
  await expect(job).toContainText("已成功", { timeout: 15000 })
  await expect(job).toContainText("同步 2 条 · 截至 2026-09-29")
})

import { expect, test } from "@playwright/test"

test("后台任务分页、刷新失败恢复及桌面和窄屏布局", async ({ page }, testInfo) => {
  await page.goto("/login")
  await page.getByLabel("用户名").fill("admin")
  await page.getByLabel("密码").fill("change-this-admin-password")
  await page.getByRole("button", { name: "登录", exact: true }).click()
  await expect(page).toHaveURL(/\/$/)
  let fail = false
  const requested: number[] = []
  await page.route("**/api/v1/admin/jobs?*", async (route) => {
    const current = Number(new URL(route.request().url()).searchParams.get("page"))
    requested.push(current)
    if (fail) {
      await route.fulfill({ status: 503, json: { error: { message: "后台任务暂不可用" } } })
      return
    }
    await route.fulfill({
      json: {
        data: {
          items: Array.from({ length: current === 3 ? 5 : 20 }, (_, index) => ({
            id: `job-${current}-${index}`,
            job_type: `第${current}页任务${index + 1}`,
            status: "succeeded",
            available_at: "2026-09-29T08:00:00Z",
            attempt_count: 1,
          })),
          total: 45,
          page: current,
          page_size: 20,
        },
      },
    })
  })
  await page.goto("/admin/jobs")
  await expect(page.getByText("共 45 个任务 · 第 1 / 3 页 · 按计划时间倒序")).toBeVisible()
  await expect(page.getByRole("button", { name: "上一页" })).toBeDisabled()
  await page.getByRole("button", { name: "下一页" }).click()
  await expect(page.getByRole("cell", { name: "第2页任务1", exact: true })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath("jobs-desktop.png"), fullPage: true })
  await page.getByRole("spinbutton", { name: "跳转页码" }).fill("3")
  await page.getByRole("button", { name: "跳转", exact: true }).click()
  await expect(page.getByRole("button", { name: "下一页" })).toBeDisabled()
  await expect(page.getByRole("row")).toHaveCount(6)
  await page.setViewportSize({ width: 360, height: 900 })
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    .toBeTruthy()
  await page.screenshot({ path: testInfo.outputPath("jobs-mobile.png"), fullPage: true })
  fail = true
  await page.getByRole("button", { name: "上一页" }).click()
  await expect(page.getByText("无法加载后台任务")).toBeVisible({ timeout: 20000 })
  fail = false
  await page.getByRole("button", { name: "重试" }).click()
  await expect(page.getByText("共 45 个任务 · 第 2 / 3 页 · 按计划时间倒序")).toBeVisible()
  expect(requested).toContain(3)
})

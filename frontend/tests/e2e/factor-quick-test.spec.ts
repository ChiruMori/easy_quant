import { expect, test } from "@playwright/test"

test("因子快测弹窗的等待、失败重试、结果与窄屏布局", async ({ page }, testInfo) => {
  await page.goto("/login")
  await page.getByLabel("用户名").fill("admin")
  await page.getByLabel("密码").fill("change-this-admin-password")
  await page.getByRole("button", { name: "登录", exact: true }).click()
  await expect(page).toHaveURL(/\/$/)
  await page.goto("/factors")
  await page.getByLabel("搜索因子").fill("technical.ma")
  await page.getByRole("button", { name: "快速测试", exact: true }).first().click()
  const dialog = page.getByRole("dialog")
  await dialog.getByLabel("决策日期").fill("2026-09-25")
  await dialog.getByLabel("symbol · 证券代码").fill("000001")
  let attempt = 0
  let release: () => void = () => {}
  const pending = new Promise<void>((resolve) => {
    release = resolve
  })
  await page.route("**/api/v1/factors/technical.ma/quick-test", async (route) => {
    attempt += 1
    expect(route.request().postDataJSON()).toEqual({
      trading_day: "2026-09-25",
      parameters: { symbol: "000001", window: "5" },
    })
    if (attempt === 1) {
      await pending
      await route.fulfill({
        status: 409,
        json: { error: { code: "state_conflict", message: "因子快速测试超时，已终止" } },
      })
    } else {
      await route.fulfill({
        json: {
          data: {
            result: { available: true, value: 12.5 },
            rows: 5,
            elapsed_ms: 12,
            decision_at: "2026-09-25",
          },
        },
      })
    }
  })
  await dialog.getByRole("button", { name: "运行测试" }).click()
  await expect(page.getByRole("alertdialog", { name: "正在处理，请稍候" })).toBeVisible()
  release()
  await expect(dialog.getByText("因子快速测试超时，已终止", { exact: true })).toBeVisible()
  await dialog.getByRole("button", { name: "运行测试" }).click()
  await expect(dialog.getByLabel("因子测试结果")).toContainText('"value": 12.5')
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.screenshot({
    path: testInfo.outputPath("factor-quick-test-desktop.png"),
    fullPage: true,
  })
  await page.setViewportSize({ width: 360, height: 800 })
  await expect(dialog).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360)
  await page.screenshot({
    path: testInfo.outputPath("factor-quick-test-mobile.png"),
    fullPage: true,
  })
})

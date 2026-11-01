import { expect, test } from "@playwright/test"

for (const width of [1440, 360]) {
  test(`数据来源卡片唯一且配置失败恢复 ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 })
    await page.goto("/login")
    await page.getByLabel("用户名", { exact: true }).fill("admin")
    await page.getByLabel("密码", { exact: true }).fill("change-this-admin-password")
    await page.getByRole("button", { name: "登录", exact: true }).click()
    await expect(page).toHaveURL(/\/$/)
    const response = page.waitForResponse("**/api/v1/admin/market-data/datasets")
    await page.goto("/admin/data")
    const datasets = (await (await response).json()).data as Array<{ key: string; name: string }>
    const sources = page.getByRole("complementary", { name: "数据来源" })
    await expect(sources.locator('[id^="dataset-"]')).toHaveCount(
      new Set(datasets.map((row) => row.key)).size,
    )
    for (const row of datasets)
      await expect(sources.locator(`[id="dataset-${row.key}"]`)).toHaveCount(1)
    const card = sources.locator('[id="dataset-daily-bars"]')
    const toggle = card.getByRole("button", { name: "AKShare 已启用", exact: true })
    await expect(toggle).toHaveAttribute("aria-pressed", "true")
    let failed = false
    await page.route("**/api/v1/admin/market-data/datasets/daily-bars/sources", (route) => {
      if (!failed) {
        failed = true
        return route.fulfill({ status: 503, json: { error: { message: "来源配置保存暂不可用" } } })
      }
      return route.continue()
    })
    await toggle.click()
    await expect(card.getByRole("alert")).toContainText("已恢复原配置")
    await expect(toggle).toHaveAttribute("aria-pressed", "true")
    await toggle.click()
    const disabled = card.getByRole("button", { name: "AKShare 已停用", exact: true })
    await expect(disabled).toBeEnabled()
    await expect(disabled).toHaveAttribute("aria-pressed", "false")
    await page.reload()
    await expect(disabled).toBeVisible()
    await disabled.click()
    await expect(toggle).toBeEnabled()
    await expect(toggle).toHaveAttribute("aria-pressed", "true")
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    )
    await page.screenshot({ path: testInfo.outputPath(`sources-${width}.png`), fullPage: true })
  })
}

import { expect, test } from "@playwright/test"

for (const width of [1440, 360]) {
  test(`K 线复权切换与失败恢复 ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 })
    await page.goto("/login")
    await page.getByLabel("用户名", { exact: true }).fill("admin")
    await page.getByLabel("密码", { exact: true }).fill("change-this-admin-password")
    await page.getByRole("button", { name: "登录", exact: true }).click()
    await expect(page).toHaveURL(/\/$/)
    const requested: string[] = []
    let failForward = true
    await page.route("**/api/v1/admin/market-data/instruments/000001", (route) =>
      route.fulfill({
        json: { data: { symbol: "000001", name: "复权测试", exchange: "SZ", status: "active" } },
      }),
    )
    await page.route("**/api/v1/admin/market-data/instruments/000001/daily-bars?*", (route) => {
      const mode = new URL(route.request().url()).searchParams.get("adjustment") ?? "raw"
      requested.push(mode)
      if (mode === "qfq" && failForward) {
        failForward = false
        return route.fulfill({ status: 409, json: { error: { message: "价格事件需重新整理" } } })
      }
      const price = mode === "raw" ? 10 : mode === "qfq" ? 9 : 11
      return route.fulfill({
        json: {
          data: [
            {
              symbol: "000001",
              trading_day: "2026-09-21",
              open: String(price),
              high: String(price),
              low: String(price),
              close: String(price),
              volume: "100",
              amount: "1000",
            },
          ],
        },
      })
    })
    await page.goto("/admin/data/instruments/000001")
    await expect(page.getByRole("tab", { name: "前复权", exact: true })).toHaveAttribute(
      "data-state",
      "active",
    )
    await expect(page.getByText("价格事件需重新整理")).toBeVisible()
    await expect(page.getByRole("img", { name: "可缩放和拖动的 K 线图" })).toHaveCount(0)
    await page.getByRole("button", { name: "重试日线" }).click()
    await expect(page.getByRole("img", { name: "可缩放和拖动的 K 线图" })).toBeVisible()
    for (const name of ["不复权", "后复权", "前复权"]) {
      await page.getByRole("tab", { name, exact: true }).click()
      await expect(page.getByRole("tab", { name, exact: true })).toHaveAttribute(
        "data-state",
        "active",
      )
      await expect(page.getByRole("img", { name: "可缩放和拖动的 K 线图" })).toBeVisible()
    }
    expect(requested).toContain("qfq")
    expect(requested).toContain("raw")
    expect(requested).toContain("hfq")
    await page.getByRole("radio", { name: "周 K" }).click()
    await expect(page.getByRole("radio", { name: "周 K" })).toHaveAttribute("data-state", "on")
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBeTruthy()
    await page.screenshot({
      path: testInfo.outputPath(`price-adjustment-${width}.png`),
      fullPage: true,
    })
  })
}

import { expect, test } from "@playwright/test"

for (const width of [1440, 360]) {
  test(`聚合采集进度与失败恢复 ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 })
    let failing = true
    await page.route("**/api/v1/**", (route) => {
      const path = new URL(route.request().url()).pathname.replace("/api/v1", "")
      if (path === "/auth/me")
        return route.fulfill({
          json: {
            data: { user: { id: "a", username: "管理员", role: "admin", status: "active" } },
          },
        })
      if (path === "/admin/jobs") {
        if (failing)
          return route.fulfill({ status: 503, json: { error: { message: "任务暂时不可用" } } })
        return route.fulfill({
          json: {
            data: {
              items: [
                {
                  id: "one",
                  job_type: "market-data-collection",
                  status: "queued",
                  available_at: "2026-11-01T12:00:00Z",
                  attempt_count: 5,
                  result_summary: {
                    collection: true,
                    message: "串行采集中；每次请求至少间隔5秒",
                    completed_units: 2,
                    total_units: 150,
                    dataset_key: "balance-sheets",
                    report_period: "2026-09-30",
                    page: 3,
                    record_count: 1000,
                    unchanged_count: 8,
                    failed_datasets: [],
                  },
                  error_summary: {},
                },
              ],
              total: 1,
              page: 1,
              page_size: 20,
            },
          },
        })
      }
      if (path === "/admin/market-data/coverage")
        return route.fulfill({
          json: {
            data: {
              instrument_count: 0,
              total: 0,
              items: [],
              page: 1,
              page_size: 50,
              recommended_end_day: "2026-10-30",
              calendar_estimated: false,
            },
          },
        })
      return route.fulfill({ json: { data: [] } })
    })
    await page.goto("/admin/jobs")
    await expect(page.getByText("任务暂时不可用", { exact: true })).toBeVisible()
    failing = false
    await page.getByRole("button", { name: "重试", exact: true }).click()
    await expect(page.getByText("盘后聚合数据采集", { exact: true })).toBeVisible()
    await expect(page.getByText(/保存 1000 条/)).toBeVisible()
    await expect(page.getByText("共 1 个任务", { exact: false })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    )
    await page.screenshot({ path: testInfo.outputPath(`collection-${width}.png`), fullPage: true })
    await page.goto("/admin/data")
    await expect(page.getByRole("button", { name: "数据维护" })).toBeVisible()
    await expect(page.getByText("自动采集已启用", { exact: true })).toHaveCount(0)
    await expect(page.getByRole("link", { name: "管理自动采集", exact: true })).toHaveCount(0)
  })
}

import { expect, test } from "@playwright/test"

for (const width of [1440, 360]) {
  test(`自动采集状态可发现、失败恢复与计划入口 ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 })
    let failing = true
    let enabled = true
    await page.route("**/api/v1/**", (route) => {
      const path = new URL(route.request().url()).pathname.replace("/api/v1", "")
      if (path === "/auth/me")
        return route.fulfill({
          json: {
            data: { user: { id: "a", username: "管理员", role: "admin", status: "active" } },
          },
        })
      if (path === "/admin/schedules") {
        if (failing)
          return route.fulfill({ status: 503, json: { error: { message: "计划状态暂时不可用" } } })
        return route.fulfill({
          json: {
            data: [
              {
                id: "auto",
                task_type: "market-data-nightly",
                enabled,
                schedule_kind: "cron",
                schedule_expression: "0 22 * * 1-5",
                timezone: "Asia/Shanghai",
                next_run_at: "2026-11-02T14:00:00+00:00",
                configuration: {},
              },
            ],
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
      if (path === "/admin/jobs")
        return route.fulfill({ json: { data: { items: [], total: 0, page: 1, page_size: 20 } } })
      return route.fulfill({ json: { data: [] } })
    })
    await page.goto("/admin/data")
    await expect(
      page.getByText("无法读取自动采集状态：计划状态暂时不可用", { exact: true }),
    ).toBeVisible()
    failing = false
    await page.getByRole("button", { name: "重试采集状态", exact: true }).click()
    await expect(page.getByText("自动采集已启用", { exact: true })).toBeVisible()
    await expect(page.getByText(/下次执行：2026\/11\/02 22:00:00/)).toBeVisible()
    await expect(page.getByText(/三大财报、财务指标、公司概况/)).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    )
    await page.screenshot({ path: testInfo.outputPath(`automatic-${width}.png`), fullPage: true })
    await page.getByRole("link", { name: "管理自动采集", exact: true }).click()
    await expect(page).toHaveURL(/\/admin\/schedules$/)
    await expect(page.getByRole("heading", { name: "定时任务", exact: true })).toBeVisible()
    enabled = false
    await page.goto("/admin/data")
    await page.reload()
    await expect(page.getByText("自动采集已停用", { exact: true })).toBeVisible()
    await expect(page.getByText(/已有停用配置已保留/)).toBeVisible()
    await page.getByRole("link", { name: "查看采集任务", exact: true }).click()
    await expect(page).toHaveURL(/\/admin\/jobs$/)
  })
}

import { expect, test } from "@playwright/test"

for (const width of [1440, 360]) {
  test(`报表指标、主营分类和缺失数据 ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 })
    let failed = false
    await page.route("**/api/v1/**", (route) => {
      const path = new URL(route.request().url()).pathname
      if (path.endsWith("/auth/me"))
        return route.fulfill({
          json: { data: { user: { id: "u", username: "研究员", role: "user", status: "active" } } },
        })
      if (path.includes("/reports/")) {
        const business = path.endsWith("business-compositions")
        if (!business && !failed) {
          failed = true
          return route.fulfill({ status: 503, json: { error: { message: "图表暂不可用" } } })
        }
        return route.fulfill({
          json: {
            data: {
              source: "eastmoney",
              sources: ["eastmoney", "sina"],
              as_of: "2026-11-14T00:00:00+08:00",
              items: business
                ? [
                    {
                      record_key: "product",
                      report_period: "2025-12-31",
                      item_name: "电子产品",
                      category: "2",
                      business_revenue: "200000000",
                      business_cost: null,
                    },
                    {
                      record_key: "region",
                      report_period: "2025-12-31",
                      item_name: "中国大陆",
                      category: "3",
                      business_revenue: "200000000",
                    },
                  ]
                : [
                    {
                      record_key: "2025",
                      report_period: "2025-12-31",
                      statement_scope: "合并",
                      parent_net_profit: "200000000",
                      revenue: "400000000",
                    },
                  ],
            },
          },
        })
      }
      if (path.endsWith("/daily-bars")) return route.fulfill({ json: { data: [] } })
      if (path.endsWith("/fundamentals"))
        return route.fulfill({ json: { data: { symbol: "000001", fields: {}, datasets: [] } } })
      if (path.includes("/fundamentals/"))
        return route.fulfill({ json: { data: { items: [], total: 0 } } })
      if (path.endsWith("/instruments/000001"))
        return route.fulfill({
          json: {
            data: { symbol: "000001", name: "测试证券", exchange: "深交所", status: "active" },
          },
        })
      return route.fulfill({ status: 404, json: { error: { message: "未定义 fixture" } } })
    })
    await page.goto("/instruments/000001")
    await expect(page.getByText("图表暂不可用")).toBeVisible()
    await page.getByRole("button", { name: "重试报表图表", exact: true }).click()
    await expect(
      page.getByRole("img", { name: "归母净利润报表图，单位亿元，缺失值留空" }),
    ).toBeVisible()
    await page.getByLabel("财务指标", { exact: true }).click()
    await page.getByRole("option", { name: "营业收入", exact: true }).click()
    await expect(
      page.getByRole("img", { name: "营业收入报表图，单位亿元，缺失值留空" }),
    ).toBeVisible()
    await page.getByText("查看图表数值与缺失项", { exact: true }).first().click()
    await expect(page.getByRole("cell", { name: "数据缺失", exact: true }).first()).toBeVisible()
    await page.getByLabel("主营报告期", { exact: true }).click()
    await page.getByRole("option", { name: "2025-12-31", exact: true }).click()
    await expect(
      page.getByRole("img", { name: "主营收入报表图，单位亿元，缺失值留空" }),
    ).toBeVisible()
    await page.getByLabel("构成分类", { exact: true }).click()
    await page.getByRole("option", { name: "按地区", exact: true }).click()
    await expect(page.getByText("中国大陆", { exact: true }).first()).toBeVisible()
    await expect(page.getByRole("button", { name: /补采财报|补采主营/ })).toHaveCount(0)
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBeTruthy()
    await page.screenshot({ path: testInfo.outputPath(`reports-${width}.png`), fullPage: true })
  })
}

test("管理员补采所选单股报告期，提交失败和任务失败可重试", async ({ page }) => {
  let attempts = 0
  let payload: unknown
  await page.route("**/api/v1/**", (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith("/auth/me"))
      return route.fulfill({
        json: {
          data: { user: { id: "admin", username: "管理员", role: "admin", status: "active" } },
        },
      })
    if (path.endsWith("/acquisitions") && route.request().method() === "POST") {
      payload = route.request().postDataJSON()
      attempts++
      if (attempts === 1)
        return route.fulfill({ status: 503, json: { error: { message: "提交失败，请重试" } } })
      return route.fulfill({ json: { data: { id: "repair", status: "queued" } } })
    }
    if (path.endsWith("/acquisitions/repair"))
      return route.fulfill({
        json: {
          data: { id: "repair", status: "failed", message: "000001 来源暂不可用", record_count: 0 },
        },
      })
    if (path.includes("/reports/"))
      return route.fulfill({
        json: { data: { source: "", sources: [], as_of: "2026-11-14T00:00:00+08:00", items: [] } },
      })
    if (path.endsWith("/daily-bars")) return route.fulfill({ json: { data: [] } })
    if (path.endsWith("/fundamentals"))
      return route.fulfill({ json: { data: { fields: {}, datasets: [] } } })
    if (path.includes("/fundamentals/"))
      return route.fulfill({ json: { data: { items: [], total: 0 } } })
    if (path.endsWith("/instruments/000001"))
      return route.fulfill({
        json: { data: { symbol: "000001", name: "测试证券", status: "active" } },
      })
    return route.fulfill({ status: 404, json: { error: { message: "fixture未定义" } } })
  })
  await page.goto("/instruments/000001")
  const button = page.getByRole("button", { name: "补采财报 2026-09-30", exact: true })
  await button.click()
  await expect(page.getByText("提交失败，请重试", { exact: true })).toBeVisible()
  await button.click()
  await expect(page.getByText(/补采部分失败，成功数据已保留：000001/)).toBeVisible()
  await expect(button).toBeEnabled()
  expect(payload).toEqual({
    dataset_key: "income-statements",
    force: true,
    symbols: ["000001"],
    start_day: "2026-09-30",
    end_day: "2026-09-30",
  })
})

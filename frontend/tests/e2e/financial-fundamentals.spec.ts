import { expect, test } from "@playwright/test"

test("管理员按报告期同步三表并查看部分失败股票", async ({ page }) => {
  let submitted: unknown
  const task = {
    id: "finance-task",
    dataset_key: "balance-sheets",
    status: "failed",
    record_count: 2,
    message: "部分股票财务数据同步失败，已保留其他成功股票",
    failed_symbols: [{ symbol: "000002", message: "来源暂时不可用" }],
    attempts: [
      {
        symbol: "000002",
        source_key: "eastmoney",
        attempt: 1,
        status: "failed",
        message: "上游失败",
      },
    ],
  }
  await page.route("**/api/v1/**", (route) => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "")
    if (path === "/auth/me")
      return route.fulfill({
        json: {
          data: { user: { id: "admin", username: "管理员", role: "admin", status: "active" } },
        },
      })
    if (path === "/admin/market-data/datasets")
      return route.fulfill({
        json: {
          data: [
            "balance-sheets",
            "income-statements",
            "cash-flow-statements",
            "financial-indicators",
            "company-profiles",
            "dividend-plans",
            "shareholder-counts",
            "business-compositions",
          ].map((key, index) => ({
            key,
            name: [
              "资产负债表",
              "利润表",
              "现金流量表",
              "主要财务指标",
              "公司概况",
              "分红送配",
              "股东户数与股本",
              "主营构成",
            ][index],
            sources: [],
          })),
        },
      })
    if (path === "/admin/market-data/acquisitions" && route.request().method() === "POST") {
      submitted = route.request().postDataJSON()
      return route.fulfill({ json: { data: { ...task, status: "queued" } } })
    }
    if (path === "/admin/market-data/acquisitions/finance-task")
      return route.fulfill({ json: { data: task } })
    return route.fulfill({ status: 404, json: { error: { message: "fixture未定义" } } })
  })
  await page.goto("/admin/data/acquisitions")
  await page.getByRole("combobox", { name: "数据集", exact: true }).click()
  await page.getByRole("option", { name: "资产负债表", exact: true }).click()
  await page.getByLabel("证券代码（指数加 sh/sz 前缀）", { exact: true }).fill("000001,000002")
  await page.getByLabel("开始日期", { exact: true }).fill("2020-01-01")
  await page.getByLabel("结束日期", { exact: true }).fill("2026-09-30")
  await page.getByRole("button", { name: "开始同步", exact: true }).click()
  await expect(page.getByText("000002 · 来源暂时不可用", { exact: true })).toBeVisible()
  expect(submitted).toMatchObject({
    dataset_key: "balance-sheets",
    symbols: ["000001", "000002"],
    start_day: "2020-01-01",
    end_day: "2026-09-30",
    force: true,
  })
  await expect(page.getByText(/000002 · eastmoney/)).toBeVisible()
})

for (const width of [1440, 360]) {
  test(`股票基本面目录、完整科目、分页与失败恢复 ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 })
    const names: Record<string, string> = {
      "financial-indicators": "主要财务指标",
      "balance-sheets": "资产负债表",
      "income-statements": "利润表",
      "cash-flow-statements": "现金流量表",
      "company-profiles": "公司概况",
      "dividend-plans": "分红送配",
      "shareholder-counts": "股东户数与股本",
      "business-compositions": "主营构成",
      "market-values": "估值与市值",
      "pledge-ratios": "股票质押率",
      "sw-industry-memberships": "申万行业归属",
      "security-status": "证券状态与风险",
    }
    let overviewFailed = false
    let recordsFailed = false
    await page.route("**/api/v1/**", (route) => {
      const url = new URL(route.request().url())
      const path = url.pathname.replace("/api/v1", "")
      if (path === "/auth/me")
        return route.fulfill({
          json: { data: { user: { id: "u", username: "研究员", role: "user", status: "active" } } },
        })
      if (path.endsWith("/fundamentals")) {
        if (!overviewFailed) {
          overviewFailed = true
          return route.fulfill({
            status: 503,
            json: { error: { message: "基本面目录暂时不可用" } },
          })
        }
        return route.fulfill({
          json: {
            data: {
              symbol: "000001",
              as_of: "2026-11-01T00:00:00+08:00",
              fields: {
                roe: { label: "加权净资产收益率", unit: "%" },
                total_assets: { label: "资产总计", unit: "元" },
              },
              datasets: Object.entries(names).map(([key, name]) => ({
                key,
                name,
                count: key === "dividend-plans" ? 0 : 6,
              })),
            },
          },
        })
      }
      if (path.includes("/fundamentals/")) {
        const dataset = path.split("/").at(-1)!
        if (dataset === "balance-sheets" && !recordsFailed) {
          recordsFailed = true
          return route.fulfill({ status: 503, json: { error: { message: "报表读取暂时失败" } } })
        }
        const second = url.searchParams.get("page") === "2"
        return route.fulfill({
          json: {
            data: {
              total: dataset === "dividend-plans" ? 0 : 6,
              page_size: 5,
              page: second ? 2 : 1,
              items:
                dataset === "dividend-plans"
                  ? []
                  : [
                      {
                        record_key: `${dataset}-${second}`,
                        report_period: second ? "2025-12-31" : "2026-06-30",
                        report_type: second ? "年报" : "中报",
                        source: "eastmoney",
                        available_at: "2026-08-01T23:59:59+08:00",
                        availability_basis: "source_revision",
                        roe: "8.07",
                        total_assets: "1234567890.12",
                        period_basis: "年初至报告期累计",
                        raw_fields: {
                          VERY_LONG_INDUSTRY_SPECIFIC_FIELD: "987654321.123456789",
                          OTHER_BANK_ITEM: "456.00",
                        },
                        field_labels: {
                          VERY_LONG_INDUSTRY_SPECIFIC_FIELD: "行业特有的完整原始科目",
                        },
                      },
                    ],
            },
          },
        })
      }
      if (path.endsWith("/daily-bars")) return route.fulfill({ json: { data: [] } })
      if (path === "/market-data/instruments/000001")
        return route.fulfill({
          json: {
            data: {
              symbol: "000001",
              name: "平安银行",
              exchange: "深圳证券交易所",
              status: "active",
              listed_on: "1991-04-03",
            },
          },
        })
      return route.fulfill({ status: 404, json: { error: { message: "fixture未定义" } } })
    })
    await page.goto("/instruments/000001")
    await expect(page.getByRole("heading", { name: "000001 平安银行" })).toBeVisible()
    await expect(page.getByText("基本面目录暂时不可用", { exact: true })).toBeVisible()
    await page.getByRole("button", { name: "重试基本面", exact: true }).click()
    await expect(page.getByText("加权净资产收益率（%）", { exact: true })).toBeVisible()
    await expect(page.getByText("8.07", { exact: true })).toBeVisible()
    await page.getByRole("button", { name: "查看全部来源科目（原始口径）" }).click()
    await expect(page.getByText("987654321.123456789", { exact: true })).toBeVisible()
    await page.getByRole("button", { name: "下一页", exact: true }).click()
    await expect(page.getByText(/第 2 页/)).toBeVisible()
    await expect(page.getByRole("button", { name: "下一页", exact: true })).toBeDisabled()
    const select = page.getByRole("combobox", { name: "查看数据集" })
    await select.click()
    await page.getByRole("option", { name: "资产负债表（6）", exact: true }).click()
    await expect(page.getByText("报表读取暂时失败", { exact: true })).toBeVisible()
    await page.getByRole("button", { name: "重试记录", exact: true }).click()
    await expect(page.getByText("资产总计（元）", { exact: true })).toBeVisible()
    await expect(page.getByText(/第 1 页/)).toBeVisible()
    for (const name of [
      "利润表",
      "现金流量表",
      "公司概况",
      "股东户数与股本",
      "主营构成",
      "估值与市值",
      "股票质押率",
      "申万行业归属",
      "证券状态与风险",
    ]) {
      await select.click()
      await page.getByRole("option", { name: `${name}（6）`, exact: true }).click()
      await expect(page.getByText("加权净资产收益率（%）", { exact: true })).toBeVisible()
    }
    await page.getByRole("button", { name: "查看全部来源科目（原始口径）" }).click()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    )
    await page.screenshot({
      path: testInfo.outputPath(`fundamentals-${width}.png`),
      fullPage: true,
    })
    await select.click()
    await page.getByRole("option", { name: "分红送配（0）", exact: true }).click()
    await expect(
      page.getByText("该数据集尚无已保存记录。管理员可在“范围拉取”中同步。", { exact: true }),
    ).toBeVisible()
    await expect(page.getByRole("button", { name: "标记停牌" })).toHaveCount(0)
  })
}

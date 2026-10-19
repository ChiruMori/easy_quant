import { expect, type Page, test } from "@playwright/test"

async function login(page: Page) {
  await page.goto("/login")
  await page.getByLabel("用户名").fill("admin")
  await page.getByLabel("密码").fill("change-this-admin-password")
  await page.getByRole("button", { name: "登录", exact: true }).click()
  await expect(page).toHaveURL(/\/$/)
}

test("窄视口分页控件不重叠且可跳页", async ({ page }) => {
  await page.setViewportSize({ width: 740, height: 900 })
  await login(page)
  await page.route("**/api/v1/admin/market-data/coverage?**", (route) =>
    route.fulfill({
      json: {
        data: {
          instrument_count: 6001,
          total: 6001,
          page: Number(new URL(route.request().url()).searchParams.get("page") ?? "1"),
          page_size: 50,
          next_cursor: "000001",
          previous_cursor: "000001",
          items: [
            {
              symbol: "000001",
              name: "平安银行",
              exchange: "深圳证券交易所",
              first_trading_day: null,
              last_trading_day: null,
              record_count: 0,
              sync_status: "未同步",
              freshness_status: "not_updated",
              updated: false,
              stale: false,
              previous_trading_day: "2026-09-29",
              recommended_end_day: "2026-09-30",
            },
          ],
        },
      },
    }),
  )
  await page.goto("/admin/data")
  const controls = [
    page.getByRole("button", { name: "上一页" }),
    page.getByRole("button", { name: "下一页" }),
    page.getByLabel("页码"),
    page.getByRole("button", { name: "跳转" }),
  ]
  await expect(controls[3]).toBeVisible()
  const boxes = await Promise.all(controls.map((control) => control.boundingBox()))
  for (const box of boxes) {
    expect(box).not.toBeNull()
    expect(box!.x).toBeGreaterThanOrEqual(0)
    expect(box!.x + box!.width).toBeLessThanOrEqual(740)
  }
  for (let index = 1; index < boxes.length; index += 1) {
    expect(
      boxes[index]!.x >= boxes[index - 1]!.x + boxes[index - 1]!.width ||
        boxes[index]!.y >= boxes[index - 1]!.y + boxes[index - 1]!.height,
    ).toBe(true)
  }
  await controls[2].fill("120")
  await controls[3].click()
  await expect(page.getByText(/第 120 \/ 121 页/)).toBeVisible()
})

test("股票详情可切换日周月 K 线", async ({ page }) => {
  await login(page)
  await page.goto("/admin/data/import")
  await page.getByLabel("选择 CSV 文件").setInputFiles({
    name: "bars.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "symbol,trading_day,open,high,low,close,volume\n" +
        "000001,2026-09-28,10,11,9,10.5,1000\n" +
        "000001,2026-09-29,10.5,12,10,11,1200",
    ),
  })
  await expect(page.getByText(/预检通过/)).toBeVisible()
  await page.getByRole("button", { name: "确认导入" }).click()
  await expect(page.getByText(/已导入/)).toBeVisible()
  await page.goto("/admin/data/instruments/000001")
  await expect(page.getByRole("img", { name: "可缩放和拖动的 K 线图" })).toBeVisible()
  for (const period of ["周 K", "月 K", "日 K"]) {
    await page.getByRole("radio", { name: period }).click()
    await expect(page.getByRole("radio", { name: period })).toHaveAttribute("data-state", "on")
  }
  await page.getByLabel("状态依据").fill("交易所停牌公告")
  await page.getByRole("button", { name: "标记停牌" }).click()
  await expect(page.getByText("已停牌")).toBeVisible()
  await page.goto("/admin/data")
  await page.getByLabel("名称或代码").fill("000001")
  await page.getByRole("button", { name: "搜索" }).click()
  await expect(page.getByRole("table").getByText("已停牌")).toBeVisible()
  const row = page.getByRole("row").filter({ hasText: "000001" })
  await expect(row.getByText("数据落后")).toHaveCount(0)
  await expect(row.getByText("已过时")).toHaveCount(0)
  await expect(row.getByText("来源尚未发布新数据")).toHaveCount(0)
  await expect(page.getByRole("button", { name: /更新至/ })).toHaveCount(0)
})

test("批量刷新停复牌状态后更新覆盖，无需拉取日线", async ({ page }) => {
  await login(page)
  let refreshed = false
  await page.route("**/api/v1/admin/market-data/coverage?**", (route) =>
    route.fulfill({
      json: {
        data: {
          instrument_count: 1,
          total: 1,
          page: 1,
          page_size: 50,
          recommended_end_day: "2026-10-14",
          items: [
            {
              symbol: "600293",
              name: "三峡新材",
              exchange: "上海证券交易所",
              status: refreshed ? "suspended" : "active",
              first_trading_day: "2000-09-19",
              last_trading_day: "2026-09-28",
              record_count: 6000,
              sync_status: refreshed ? "已停牌" : "数据落后",
              stale: !refreshed,
              recommended_end_day: "2026-10-14",
            },
          ],
        },
      },
    }),
  )
  await page.route("**/api/v1/admin/market-data/acquisitions", async (route) => {
    expect(route.request().postDataJSON()).toMatchObject({
      dataset_key: "trading-status",
      end_day: "2026-10-14",
    })
    await route.fulfill({
      json: { data: { id: "suspension", dataset_key: "trading-status", status: "queued" } },
    })
  })
  await page.route("**/api/v1/admin/market-data/acquisitions/suspension", async (route) => {
    refreshed = true
    await route.fulfill({
      json: {
        data: {
          id: "suspension",
          dataset_key: "trading-status",
          status: "succeeded",
          record_count: 1,
          message: "已确认 1 只股票整日停牌",
        },
      },
    })
  })
  await page.goto("/admin/data")
  await expect(page.getByRole("button", { name: "更新至 2026-10-14" })).toBeVisible()
  await page.getByRole("button", { name: "数据维护" }).click()
  await page.getByRole("menuitem", { name: "刷新停复牌状态" }).click()
  expect(refreshed).toBe(false)
  await page.getByRole("button", { name: "确认刷新停复牌状态" }).click()
  await expect(page.getByText(/已确认 1 只股票整日停牌/)).toBeVisible()
  await expect(page.getByRole("table").getByText("已停牌")).toBeVisible()
  await expect(page.getByRole("button", { name: /更新至/ })).toHaveCount(0)
})

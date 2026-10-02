import { expect, test } from "@playwright/test"

test("因子—策略保存运行—回测—实盘的真实前后端旅程", async ({ page }) => {
  await page.goto("/login")
  await page.getByLabel("用户名").fill("admin")
  await page.getByLabel("密码").fill("change-this-admin-password")
  await page.getByRole("button", { name: "登录", exact: true }).click()
  await expect(page).toHaveURL(/\/$/)

  const rows = ["symbol,trading_day,open,high,low,close,volume"]
  for (let day = new Date("2025-12-20T00:00:00Z"); day <= new Date("2026-01-31T00:00:00Z");) {
    const iso = day.toISOString().slice(0, 10)
    const close = 10 + rows.length / 100
    rows.push(`000001,${iso},${close - 0.1},${close + 0.2},${close - 0.2},${close},100000`)
    day = new Date(day.getTime() + 86_400_000)
  }
  await page.goto("/admin/data/import")
  await page.getByLabel("选择 CSV 文件").setInputFiles({
    name: "daily-bars.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(rows.join("\n")),
  })
  await expect(page.getByText(/预检通过/)).toBeVisible()
  await page.getByRole("button", { name: "确认导入" }).click()
  await expect(page.getByText(/已导入/)).toBeVisible()

  await page.goto("/admin/data")
  await page.getByLabel("名称或代码").fill("000001")
  await page.getByRole("button", { name: "搜索" }).click()
  await page.getByRole("link", { name: /000001/ }).click()
  await expect(page.getByText("日线 K 线", { exact: true })).toBeVisible()
  await expect(page.locator("main .recharts-surface")).toBeVisible()
  await expect(page.locator("main .recharts-bar-rectangle rect").first()).toBeVisible()

  await page.goto("/factors")
  await expect(page.getByRole("heading", { name: "因子目录" })).toBeVisible()
  await expect(page.getByText(/5 日均线/).first()).toBeVisible()
  await expect(page.getByText(/context\.factor/).first()).toBeVisible()

  await page.goto("/strategies")
  await page.getByRole("button", { name: "使用5 日均线选股" }).click()
  await page.getByLabel("名称").fill(`均线策略-${Date.now()}`)
  await page.getByLabel("说明").fill("通过 5 日均线因子选股")
  await page.getByRole("button", { name: "验证并创建策略" }).click()
  await expect(page.getByText("策略版本已保存")).toBeVisible()
  await page.getByLabel("快速测试交易日").fill("2026-01-30")
  await page.getByRole("button", { name: "运行当前版本" }).click()
  await expect(page.getByText("已成功")).toBeVisible()

  await page.goto("/backtests/new")
  await page.getByRole("combobox").click()
  await page.getByRole("option").last().click()
  await page.getByLabel("开始日期").fill("2026-01-01")
  await page.getByLabel("结束日期").fill("2026-01-31")
  await page.getByRole("button", { name: "开始回测" }).click()
  await expect(page.getByRole("heading", { name: "回测详情" })).toBeVisible()
  await expect(page.getByText(/状态：已完成/)).toBeVisible({ timeout: 30000 })
  await page.getByRole("button", { name: "开启实盘跟踪" }).click()
  await expect(page.getByRole("heading", { name: /实盘实例/ })).toBeVisible()
})

import { expect, test } from "@playwright/test"

test("因子—策略保存运行—回测—实盘的真实前后端旅程", async ({ page }, testInfo) => {
  await page.goto("/login")
  await page.getByLabel("用户名").fill("admin")
  await page.getByLabel("密码").fill("change-this-admin-password")
  const loginResponse = page.waitForResponse("**/api/v1/auth/login")
  await page.getByRole("button", { name: "登录", exact: true }).click()
  const csrf = (await (await loginResponse).json()).data.csrf_token
  const headers = { "X-CSRF-Token": csrf }
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
  await expect(page.getByText("K 线图", { exact: true })).toBeVisible()
  await expect(page.getByRole("img", { name: "可缩放和拖动的 K 线图" })).toBeVisible()

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
  const liveId = page.url().split("/").at(-1)
  const analysis = await page.request.post(
    `/api/v1/live-instances/${liveId}/analyze/before_market`,
    {
      headers,
      data: { decision_at: "2026-09-29T01:00:00+00:00" },
    },
  )
  expect(analysis.ok()).toBeTruthy()
  const recommendation = (await analysis.json()).data.created[0]
  expect(recommendation).toBeDefined()
  await page.reload()
  const confirmation = page.waitForResponse(
    `**/api/v1/recommendations/${recommendation.id}/confirm`,
  )
  await page.getByRole("button", { name: "快速确认" }).click()
  const confirmed = await confirmation
  expect(confirmed.ok()).toBeTruthy()
  await expect(page.getByText(/已确认/)).toBeVisible()
  await expect(page.getByRole("button", { name: "快速确认" })).toBeDisabled()
  const retry = await page.request.post(`/api/v1/recommendations/${recommendation.id}/confirm`, {
    headers,
    data: confirmed.request().postDataJSON(),
  })
  expect(retry.ok()).toBeTruthy()
  expect((await retry.json()).data).toEqual((await confirmed.json()).data)
  const portfolio = (
    await (await page.request.get(`/api/v1/recommendations/portfolio/${liveId}`)).json()
  ).data
  expect(portfolio.positions["000001"]).toBe("100")
  expect(portfolio.ledger).toHaveLength(1)
  await page.reload()
  await expect(page.getByText(/已确认/)).toBeVisible()
  await expect(page.getByRole("button", { name: "快速确认" })).toBeDisabled()

  const live = (await (await page.request.get(`/api/v1/live-instances/${liveId}`)).json()).data
  const limitedResponse = await page.request.post("/api/v1/live-instances", {
    headers,
    data: { backtest_id: live.backtest_id, initial_cash: "1" },
  })
  expect(limitedResponse.ok()).toBeTruthy()
  const limited = (await limitedResponse.json()).data
  expect(
    (
      await page.request.post(`/api/v1/live-instances/${limited.id}/analyze/before_market`, {
        headers,
        data: { decision_at: "2026-09-29T01:00:00+00:00" },
      })
    ).ok(),
  ).toBeTruthy()
  await page.goto(`/live/${limited.id}`)
  await page.getByRole("button", { name: "快速确认" }).click()
  await expect(page.getByRole("alert")).toContainText("账本产生负现金")
  const unchanged = (
    await (await page.request.get(`/api/v1/recommendations/portfolio/${limited.id}`)).json()
  ).data
  expect(unchanged.cash).toBe("1")
  expect(unchanged.ledger).toHaveLength(0)
  await expect(page.getByRole("button", { name: "修正成交" })).toBeEnabled()
  await page.getByRole("button", { name: "修正成交" }).click()
  await page.getByLabel("实际标的").fill("000001")
  await page.getByLabel("实际数量").fill("1")
  await page.getByLabel("实际价格").fill("0.5")
  await page.getByRole("button", { name: "提交修正" }).click()
  await expect(page.getByText(/已修正/)).toBeVisible()
  await expect(page.getByRole("button", { name: "快速确认" })).toBeDisabled()
  await page.reload()
  await expect(page.getByText(/已修正/)).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath("atomic-live-actions.png"), fullPage: true })
})

import { expect, test } from "@playwright/test"

test("因子—策略保存运行—回测—实盘的真实前后端旅程", async ({ page }, testInfo) => {
  test.setTimeout(90000)
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
    rows.push(`sh000300,${iso},100,110,90,100,100000`)
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
  await page.getByLabel("搜索因子").fill("alpha101_19")
  await expect(page.getByText("周度价格反转与量价相关惩罚", { exact: true })).toBeVisible()
  await expect(page.getByText(/计算逻辑：先按7日价格变化方向取反/)).toBeVisible()
  await expect(page.getByText(/结果含义：第一部分给近期下跌正号/)).toBeVisible()
  await page.setViewportSize({ width: 375, height: 812 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  )
  await page.setViewportSize({ width: 1280, height: 900 })

  await page.goto("/strategy-library")
  await expect(page.getByRole("heading", { name: "策略公共库" })).toBeVisible()
  await page.getByLabel("搜索库函数").fill("store")
  await page.locator('[data-slot="accordion-trigger"]').first().click()
  await expect(page.getByText(/context\.store\.set/).first()).toBeVisible()

  await page.goto("/strategies")
  await page.getByRole("link", { name: "新建策略" }).click()
  await page.getByRole("button", { name: "代码模板" }).click()
  await page.getByRole("menuitem", { name: "使用5 日均线选股" }).click()
  await page.getByRole("button", { name: "确认替换模板" }).click()
  await page.getByLabel("名称").fill(`均线策略-${Date.now()}`)
  await page.getByLabel("说明").fill("通过 5 日均线因子选股")
  await page.getByRole("button", { name: "创建策略" }).click()
  await expect(page).toHaveURL(/\/strategies\/[^/]+\/versions\/[^/]+\/edit\?saved=1$/)
  await expect(page.getByRole("heading", { name: /^编辑 .* · v1$/ })).toBeVisible()
  await expect(page.getByText("草稿已保存")).toBeVisible()
  await page.getByLabel("快速测试交易日").fill("2026-01-30")
  const quickRequest = page.waitForResponse(
    (response) =>
      response.url().endsWith("/strategies/quick-test") && response.request().method() === "POST",
  )
  await page.getByRole("button", { name: "运行快速测试" }).click()
  const quick = (await (await quickRequest).json()).data
  await expect
    .poll(
      async () =>
        (
          await (
            await page.request.get(`/api/v1/strategies/quick-tests/${quick.job_id ?? quick.id}`)
          ).json()
        ).data.status,
      { timeout: 15000 },
    )
    .not.toMatch(/queued|running/)
  const quickResult = (
    await (
      await page.request.get(`/api/v1/strategies/quick-tests/${quick.job_id ?? quick.id}`)
    ).json()
  ).data
  expect(quickResult.error, JSON.stringify(quickResult)).toBeFalsy()
  await expect(page.getByText("已成功")).toBeVisible()
  await expect(page.getByText("运行耗时", { exact: true })).toBeVisible()

  await page.goto("/backtests/new")
  await page.getByRole("combobox").click()
  await page.getByRole("option").last().click()
  await page.getByLabel("开始日期").fill("2026-01-01")
  await page.getByLabel("结束日期").fill("2026-01-31")
  await page.getByLabel("基准", { exact: true }).fill("000300")
  await page.getByRole("button", { name: "开始回测" }).click()
  await expect(page.getByRole("heading", { name: "回测详情" })).toBeVisible()
  await expect(page.getByText(/状态：已完成/)).toBeVisible({ timeout: 30000 })
  await expect(page.getByText("平均耗时（秒）", { exact: true })).toBeVisible()
  await expect(page.getByText(/基准：沪深300/)).toBeVisible()
  await page.getByText("预览策略代码", { exact: true }).click()
  await expect(page.locator(".monaco-editor .view-lines").first()).toContainText(
    "def before_market",
  )
  const backtestUrl = page.url()
  await page.getByRole("link", { name: "查看或编辑此策略版本" }).click()
  await expect(page).toHaveURL(/strategies\/.*\/versions\//)
  await expect(page.getByText("测试中", { exact: true })).toBeVisible()
  await page.goto(backtestUrl)
  const subscriptionResponse = await page.request.post("/api/v1/notifications/subscriptions", {
    headers,
    data: { name: "均线推送", channel: "ntfy", destination: "offline-demo" },
  })
  expect(subscriptionResponse.ok()).toBeTruthy()
  const subscription = (await subscriptionResponse.json()).data
  await expect(page.getByText("预览策略代码")).toBeVisible()
  await page.getByRole("button", { name: "开启实盘跟踪" }).click()
  await expect(page).toHaveURL(/backtests/)
  await page.getByLabel("实盘名称", { exact: true }).fill("均线实盘")
  await page.getByLabel("实盘初始资金").fill("200000")
  await page.getByLabel("均线推送", { exact: true }).check()
  await page.getByRole("button", { name: "确认启动实盘", exact: true }).click()
  await expect(page.getByRole("heading", { name: /实盘实例/ })).toBeVisible()
  const liveId = page.url().split("/").at(-1)
  const analysis = await page.request.post(
    `/api/v1/live-instances/${liveId}/analyze/before_market`,
    {
      headers,
      data: { decision_at: "2026-01-30T01:00:00+00:00" },
    },
  )
  expect(analysis.ok()).toBeTruthy()
  const recommendation = (await analysis.json()).data.created[0]
  expect(recommendation).toBeDefined()
  await page.reload()
  const confirmation = page.waitForResponse(
    `**/api/v1/recommendations/${recommendation.id}/confirm`,
  )
  await page.getByRole("button", { name: "接受建议", exact: true }).click()
  await page.getByRole("button", { name: "确认接受建议", exact: true }).click()
  const confirmed = await confirmation
  expect(confirmed.ok()).toBeTruthy()
  await expect(page.getByRole("cell", { name: "已操作", exact: true })).toBeVisible()
  await expect(page.getByRole("button", { name: "接受建议", exact: true })).toHaveCount(0)
  const retry = await page.request.post(`/api/v1/recommendations/${recommendation.id}/confirm`, {
    headers,
    data: confirmed.request().postDataJSON(),
  })
  expect(retry.ok()).toBeTruthy()
  expect((await retry.json()).data).toEqual((await confirmed.json()).data)
  const portfolio = (
    await (await page.request.get(`/api/v1/recommendations/portfolio/${liveId}`)).json()
  ).data
  expect(recommendation.ratio).toBe("0.10")
  expect(portfolio.positions["000001"]).toBe(recommendation.quantity)
  expect(portfolio.ledger).toHaveLength(1)
  await page.reload()
  await expect(page.getByRole("cell", { name: "已操作", exact: true })).toBeVisible()
  await expect(page.getByRole("button", { name: "接受建议", exact: true })).toHaveCount(0)

  const live = (await (await page.request.get(`/api/v1/live-instances/${liveId}`)).json()).data
  const limitedResponse = await page.request.post("/api/v1/live-instances", {
    headers,
    data: {
      backtest_id: live.backtest_id,
      initial_cash: "1",
      name: "小资金",
      subscription_ids: [subscription.id],
    },
  })
  expect(limitedResponse.ok()).toBeTruthy()
  const limited = (await limitedResponse.json()).data
  const limitedAnalysis = await page.request.post(
    `/api/v1/live-instances/${limited.id}/analyze/before_market`,
    { headers, data: { decision_at: "2026-01-30T01:00:00+00:00" } },
  )
  expect(limitedAnalysis.ok()).toBeTruthy()
  expect((await limitedAnalysis.json()).data.created).toEqual([])
  await page.goto(`/live/${limited.id}`)
  await expect(page.getByRole("button", { name: "接受建议", exact: true })).toHaveCount(0)
  const unchanged = (
    await (await page.request.get(`/api/v1/recommendations/portfolio/${limited.id}`)).json()
  ).data
  expect(unchanged.cash).toBe("1")
  expect(unchanged.ledger).toHaveLength(0)
  await page.screenshot({ path: testInfo.outputPath("atomic-live-actions.png"), fullPage: true })
})

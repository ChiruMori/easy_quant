import { expect, test } from "@playwright/test"

for (const width of [1440, 360]) {
  test(`实盘建议管理、风险确认与分页 ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 })
    await page.goto("/login")
    await page.getByLabel("用户名", { exact: true }).fill("admin")
    await page.getByLabel("密码", { exact: true }).fill("change-this-admin-password")
    await page.getByRole("button", { name: "登录", exact: true }).click()
    await expect(page).toHaveURL(/\/$/)
    const rows = Array.from({ length: 25 }, (_, index) => ({
      id: `r-${index}`,
      instrument_id: `000${String(index).padStart(3, "0")}`,
      action: "buy",
      quantity: "100",
      suggested_price: "10.5",
      suggested_fee: "0.315",
      reason: "这是超过十五个字的完整操作建议说明，供用户核对成交依据",
      status: "pending",
      version: 0,
      decision_at: "2026-10-21T02:00:00Z",
      operation_type: "buy_signal",
    }))
    const snapshot = {
      id: "live-ui-v1",
      name: "实盘仓位测试",
      backtest_id: "b",
      strategy_version_id: "v",
      status: "active",
      next_decision_at: "",
      initial_cash: "100000",
      portfolio: {
        cash: "100000",
        available_cash: "73742.125",
        reserved_cash: "26257.875",
        reserved_positions: { "000099": "100" },
        positions: {},
        capital_pool: "100000",
        profit: "12.50",
        return_rate: "0.000125",
        missing_symbols: [],
        valuation_note: "按已发布日线收盘价估值，收益排除注资。",
        curve: [
          { at: "2026-10-20T02:00:00Z", profit: "0", return_rate: "0" },
          { at: "2026-10-21T02:00:00Z", profit: "12.50", return_rate: "0.000125" },
        ],
      },
      operations: { items: rows.slice(0, 20), total: rows.length, page: 1, page_size: 20 },
    }
    let writes = 0
    let manualWrites = 0
    let failCorrection = true
    let recommendationWrites = 0
    await page.route("**/api/v1/live-instances/live-ui-v1**", async (route) => {
      const url = new URL(route.request().url())
      if (url.pathname.endsWith("/operations")) {
        const search = url.searchParams.get("search") ?? ""
        const status = url.searchParams.get("status") ?? ""
        const type = url.searchParams.get("operation_type") ?? ""
        const selected = rows.filter(
          (row) =>
            row.instrument_id.includes(search) &&
            (!status ||
              (status === "executed"
                ? ["confirmed", "corrected", "executed"].includes(row.status)
                : row.status === status)) &&
            (!type || row.operation_type === type),
        )
        const number = Number(url.searchParams.get("page") ?? 1)
        return route.fulfill({
          json: {
            data: {
              items: selected.slice((number - 1) * 20, number * 20),
              page: number,
              page_size: 20,
              total: selected.length,
            },
          },
        })
      }
      if (url.pathname.endsWith("/preview"))
        return route.fulfill({
          json: { data: { required_increase: "5000.3", capital_pool: "105000.3" } },
        })
      if (url.pathname.endsWith("/record")) {
        const body = route.request().postDataJSON()
        expect(body.risk_acknowledged).toBe(true)
        expect(body.confirmed_increase).toBe("5000.3")
        manualWrites++
        return route.fulfill({
          json: { data: { required_increase: "5000.3", capital_pool: "105000.3" } },
        })
      }
      if (route.request().method() === "POST") {
        writes++
        snapshot.status = url.pathname.endsWith("/pause") ? "paused" : "terminated"
      }
      return route.fulfill({ json: { data: snapshot } })
    })
    await page.route("**/api/v1/recommendations/*/correct", (route) => {
      const body = route.request().postDataJSON()
      expect(body.symbol).toBe("000000")
      expect(body.action).toBe("buy")
      expect(body.quantity).toBe("200")
      if (failCorrection) {
        failCorrection = false
        return route.fulfill({
          status: 409,
          json: { error: { code: "state_conflict", message: "可用资金不足" } },
        })
      }
      rows[0].status = "corrected"
      return route.fulfill({
        json: {
          data: { id: "op", recommendation_status: "corrected", version: 1, kind: "correct" },
        },
      })
    })
    await page.route("**/api/v1/recommendations/*/reject", (route) => {
      recommendationWrites++
      rows[1].status = "rejected"
      return route.fulfill({
        json: {
          data: { id: "rejected", recommendation_status: "rejected", version: 1, kind: "reject" },
        },
      })
    })
    await page.goto("/live/live-ui-v1")
    await expect(page.getByText("操作列表", { exact: true })).toBeVisible()
    await expect(page.getByRole("table").getByRole("row")).toHaveCount(21)
    await expect(page.getByText("12.50 元", { exact: true })).toBeVisible()
    await page.getByRole("button", { name: "下一页", exact: true }).click()
    await expect(page.getByRole("table").getByRole("row")).toHaveCount(6)
    await page.getByLabel("搜索操作").fill("000000")
    await page.getByRole("button", { name: "搜索", exact: true }).click()
    await expect(page.getByRole("table").getByRole("row")).toHaveCount(2)
    await page.getByRole("button", { name: "修正成交", exact: true }).click()
    const dialog = page.getByRole("dialog", { name: "修正成交", exact: true })
    await expect(dialog.getByText(/标的 000000 · 买入/)).toBeVisible()
    await expect(dialog.getByLabel("实际价格")).toHaveValue("10.5")
    await expect(dialog.getByLabel("手续费")).toHaveValue("0.315")
    await dialog.getByLabel("实际数量").fill("101")
    expect(
      await dialog
        .getByLabel("实际数量")
        .evaluate((node: HTMLInputElement) => node.validity.stepMismatch),
    ).toBe(true)
    await dialog.getByLabel("实际数量").fill("200")
    await dialog.getByRole("button", { name: "提交修正", exact: true }).click()
    await expect(dialog.getByRole("alert")).toContainText("可用资金不足")
    await dialog.getByRole("button", { name: "提交修正", exact: true }).click()
    await expect(dialog).toHaveCount(0)
    await page.getByRole("button", { name: /^查看完整说明/ }).hover()
    await expect(page.getByRole("dialog")).toContainText(rows[0].reason)
    await page.mouse.move(0, 0)
    await expect(page.getByRole("dialog")).toHaveCount(0)
    await page.getByLabel("搜索操作").fill("000001")
    await page.getByRole("button", { name: "搜索", exact: true }).click()
    await page.getByRole("button", { name: "接受建议", exact: true }).click()
    expect(recommendationWrites).toBe(0)
    await page.getByRole("button", { name: "取消", exact: true }).click()
    await page.getByRole("button", { name: "拒绝建议", exact: true }).click()
    expect(recommendationWrites).toBe(0)
    await page.getByRole("button", { name: "确认拒绝建议", exact: true }).click()
    await expect(page.getByRole("alertdialog")).toHaveCount(0)
    expect(recommendationWrites).toBe(1)
    await page.getByRole("combobox", { name: "操作状态", exact: true }).click()
    await page.getByRole("option", { name: "已拒绝", exact: true }).click()
    await expect(page.getByRole("cell", { name: "已拒绝", exact: true })).toBeVisible()
    await page.getByRole("combobox", { name: "操作类型", exact: true }).click()
    await page.getByRole("option", { name: "手动买入", exact: true }).click()
    await expect(page.getByText("暂无操作", { exact: true })).toBeVisible()

    await page.getByRole("button", { name: "暂停", exact: true }).click()
    expect(writes).toBe(0)
    await page.getByRole("button", { name: "取消", exact: true }).click()
    expect(writes).toBe(0)
    await page.getByRole("button", { name: "终止", exact: true }).click()
    await page.getByRole("button", { name: "取消", exact: true }).click()
    expect(writes).toBe(0)
    await page.getByRole("button", { name: "手动添加操作", exact: true }).click()
    await page.getByLabel("实际标的", { exact: true }).fill("000001")
    await page.getByLabel("实际价格", { exact: true }).fill("10")
    await page.getByRole("button", { name: "核对并继续", exact: true }).click()
    await expect(page.getByRole("alertdialog")).toContainText("追加 5000.30 元")
    expect(manualWrites).toBe(0)
    await page.getByRole("button", { name: "确认录入操作", exact: true }).click()
    await expect(page.getByRole("alertdialog")).toHaveCount(0)
    expect(manualWrites).toBe(1)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    )
    await page.screenshot({ path: testInfo.outputPath(`live-${width}.png`), fullPage: true })
  })
}

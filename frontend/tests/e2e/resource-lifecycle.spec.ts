import { expect, test } from "@playwright/test"

test("360px 日期选择、关联阻止、取消和删除失败恢复", async ({ page }, testInfo) => {
  let liveExists = true
  let channelExists = true
  let strategyExists = true
  let failLiveDeletion = true
  let deletions = 0
  const strategy = {
    id: "s",
    name: "生命周期测试策略",
    description: "",
    current_version_id: "v",
    versions: [
      {
        id: "v",
        number: 1,
        source_code: "def before_market(context, parameters):\n    return []",
        created_at: "2026-09-29T00:00:00Z",
      },
    ],
  }
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "")
    const method = route.request().method()
    const error = (message: string) =>
      route.fulfill({ status: 409, json: { error: { code: "state_conflict", message } } })
    if (method === "DELETE") {
      deletions += 1
      expect(route.request().postDataJSON()).toEqual({ confirmed: true })
      if (path === "/live-instances/l") {
        if (failLiveDeletion) {
          failLiveDeletion = false
          return error("事务失败，请重试")
        }
        liveExists = false
      }
      if (path === "/notifications/subscriptions/c") channelExists = false
      if (path === "/strategies/s/versions/v") strategyExists = false
      return route.fulfill({ json: { data: { deleted: true } } })
    }
    if (path.endsWith("/deletion-preview")) {
      if (liveExists && path !== "/live-instances/l/deletion-preview")
        return error("被实盘 稳健组合 使用，不可删除。请先手动删除相关实盘数据。")
      return route.fulfill({
        json: {
          data: {
            name: path.startsWith("/strategies") ? strategy.name : "稳健组合",
            versions: path.startsWith("/strategies") ? 1 : 0,
            quick_tests: 2,
            backtests: 3,
          },
        },
      })
    }
    const responses: Record<string, unknown> = {
      "/auth/me": { user: { id: "u", username: "研究员", role: "admin", status: "active" } },
      "/strategies": strategyExists ? [strategy] : [],
      "/strategies/templates": [],
      "/strategies/workspace": {
        items: strategyExists
          ? [
              {
                id: "s",
                version_id: "v",
                name: strategy.name,
                number: 1,
                state: "testing",
                created_at: "2026-09-29T00:00:00Z",
                live_instances: [],
              },
            ]
          : [],
        total: strategyExists ? 1 : 0,
        page: 1,
        page_size: 20,
      },
      "/strategies/s/versions/v": {
        id: "s",
        version_id: "v",
        name: strategy.name,
        number: 1,
        state: "testing",
        revision: 0,
        created_at: "2026-09-29T00:00:00Z",
        source_code: strategy.versions[0].source_code,
        live_instances: [],
      },
      "/strategies/s/runs": [],
      "/live-instances": liveExists
        ? [
            {
              id: "l",
              name: "稳健组合",
              status: "terminated",
              strategy_version_id: "v",
              next_decision_at: "2026-09-29T00:00:00Z",
              initial_cash: "100000",
            },
          ]
        : [],
      "/notifications/subscriptions": channelExists
        ? [{ id: "c", name: "实盘提醒", channel: "ntfy", enabled: false, destination: "***" }]
        : [],
      "/notifications/deliveries": [],
    }
    return route.fulfill({ json: { data: responses[path] ?? [] } })
  })
  await page.setViewportSize({ width: 360, height: 900 })
  await page.goto("/backtests/new")
  await page.getByLabel("开始日期", { exact: true }).fill("2026-09-29")
  await page.getByRole("button", { name: "选择日期 start" }).click()
  await expect(page.getByRole("grid")).toBeVisible()
  await expect(page.getByRole("grid")).toBeInViewport()
  await page.screenshot({ path: testInfo.outputPath("date-picker-360.png"), fullPage: true })
  await page.getByRole("grid").getByRole("button", { name: /30/ }).click()
  await expect(page.getByLabel("开始日期", { exact: true })).toHaveValue("2026-09-30")

  await page.goto("/notifications")
  await page.getByRole("button", { name: "删除渠道", exact: true }).click()
  await expect(page.getByRole("alert")).toContainText("稳健组合")
  await expect(page.getByRole("button", { name: "确认删除渠道" })).toBeDisabled()
  expect(deletions).toBe(0)
  await page.getByRole("button", { name: "取消" }).click()

  await page.goto("/strategies?strategy=s&version=v")
  await page.getByRole("button", { name: "删除策略", exact: true }).click()
  await expect(page.getByRole("alert")).toContainText("手动删除相关实盘数据")
  await expect(page.getByRole("button", { name: "确认删除策略" })).toBeDisabled()
  await page.getByRole("button", { name: "取消" }).click()

  await page.goto("/live")
  await page.getByRole("button", { name: "删除实盘", exact: true }).click()
  await page.getByRole("button", { name: "取消" }).click()
  expect(deletions).toBe(0)
  await page.getByRole("button", { name: "删除实盘", exact: true }).click()
  await page.getByRole("button", { name: "确认删除实盘" }).click()
  await expect(page.getByRole("alert")).toContainText("事务失败")
  await page.screenshot({ path: testInfo.outputPath("delete-failure-360.png"), fullPage: true })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  )
  await page.getByRole("button", { name: "确认删除实盘" }).click()
  await expect(page.getByText("尚未开启实盘跟踪")).toBeVisible()

  await page.goto("/notifications")
  await page.getByRole("button", { name: "删除渠道", exact: true }).click()
  await page.getByRole("button", { name: "确认删除渠道" }).click()
  await expect(page.getByRole("button", { name: "删除渠道", exact: true })).toHaveCount(0)

  await page.goto("/strategies?strategy=s&version=v")
  await page.getByRole("button", { name: "删除策略", exact: true }).click()
  await expect(page.getByRole("alertdialog")).toContainText("2 次快速测试、3 次回测")
  await page.getByRole("button", { name: "确认删除策略" }).click()
  await expect(page.getByRole("button", { name: "删除策略", exact: true })).toHaveCount(0)
  expect(deletions).toBe(4)
})

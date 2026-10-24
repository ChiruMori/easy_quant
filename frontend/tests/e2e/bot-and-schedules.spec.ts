import { expect, test } from "@playwright/test"

for (const width of [1440, 360]) {
  test(`群机器人配置显隐与测试投递、系统计划删除确认 ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 })
    await page.goto("/login")
    await page.getByLabel("用户名").fill("admin")
    await page.getByLabel("密码").fill("change-this-admin-password")
    await page.getByRole("button", { name: "登录", exact: true }).click()
    await expect(page).toHaveURL(/\/$/)
    const session = (await (await page.request.get("/api/v1/auth/me")).json()).data
    const headers = { "X-CSRF-Token": session.csrf_token }
    const schedules = new Set<string>()
    const channels = new Set<string>()
    try {
      await page.goto("/notifications")
      const bots = [
        ["钉钉机器人", "https://oapi.dingtalk.com/robot/send?access_token=fixture-ui-token", true],
        ["飞书机器人", "https://open.feishu.cn/open-apis/bot/v2/hook/fixture-ui-hook", true],
        [
          "企业微信机器人",
          "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=fixture-ui-key",
          false,
        ],
      ] as const
      for (const [label, url, signed] of bots) {
        const name = `${label}${width}-${testInfo.testId}`
        await page.getByRole("button", { name: "添加渠道", exact: true }).click()
        const dialog = page.getByRole("dialog")
        await dialog.getByLabel("渠道名称").fill(name)
        await dialog.getByRole("combobox", { name: "渠道", exact: true }).click()
        await page.getByRole("option", { name: label, exact: true }).click()
        await dialog.getByLabel("通知目标", { exact: true }).fill(url)
        if (signed) {
          await dialog.getByLabel("签名密钥（可选）").fill("fixture-ui-signing")
          await dialog.getByRole("button", { name: "显示签名密钥", exact: true }).click()
          await expect(dialog.getByLabel("签名密钥（可选）")).toHaveAttribute("type", "text")
          await dialog.getByRole("button", { name: "隐藏签名密钥", exact: true }).click()
        }
        const added = page.waitForResponse(
          (response) =>
            response.url().endsWith("/api/v1/notifications/subscriptions") &&
            response.request().method() === "POST",
        )
        await dialog.getByRole("button", { name: "添加渠道", exact: true }).click()
        const created = await added
        expect(created.ok()).toBeTruthy()
        channels.add((await created.json()).data.id)
        await expect(dialog).toHaveCount(0)
        await page.getByRole("button", { name: `测试连通性 ${name}`, exact: true }).click()
        await expect(page.getByText("测试消息已发送，请检查接收端", { exact: true })).toBeVisible()
      }
      await page.screenshot({ path: testInfo.outputPath(`robots-${width}.png`), fullPage: true })
      // 相同触发时间是合法业务数据，不得将它当作计划身份。
      const duplicate = await page.request.post("/api/v1/admin/schedules", {
        headers,
        data: {
          task_type: "market-data-nightly",
          schedule_kind: "cron",
          schedule_expression: "0 21 * * 1-5",
          timezone: "Asia/Shanghai",
          enabled: false,
          configuration: {},
        },
      })
      expect(duplicate.ok()).toBeTruthy()
      const neighbor = (await duplicate.json()).data
      schedules.add(neighbor.id)
      await page.goto("/admin/schedules")
      await expect(page.getByText(/实盘分析计划随实例启停自动更新/)).toBeVisible()
      await page.getByLabel("Cron 表达式").fill("0 21 * * 1-5")
      const saved = page.waitForResponse(
        (response) =>
          response.url().endsWith("/api/v1/admin/schedules") &&
          response.request().method() === "POST",
      )
      await page.getByRole("button", { name: "创建任务", exact: true }).click()
      const created = await saved
      expect(created.ok()).toBeTruthy()
      const schedule = (await created.json()).data
      schedules.add(schedule.id)
      const row = page.getByRole("row").and(page.getByTestId(`schedule-${schedule.id}`))
      await expect(row).toHaveCount(1)
      expect(
        await page
          .getByRole("row")
          .filter({ has: page.getByRole("cell", { name: "0 21 * * 1-5", exact: true }) })
          .count(),
      ).toBeGreaterThanOrEqual(2)
      await expect(row.getByRole("button", { name: "删除定时任务", exact: true })).toHaveCount(0)
      await row.getByRole("switch").click()
      await row.getByRole("button", { name: "删除定时任务", exact: true }).click()
      await page.getByRole("alertdialog").getByRole("button", { name: "取消", exact: true }).click()
      await expect(row).toHaveCount(1)
      await row.getByRole("button", { name: "删除定时任务", exact: true }).click()
      const deleting = page.waitForResponse(
        (response) =>
          response.url().endsWith(`/api/v1/admin/schedules/${schedule.id}`) &&
          response.request().method() === "DELETE",
      )
      await page
        .getByRole("alertdialog")
        .getByRole("button", { name: "确认删除定时任务", exact: true })
        .click()
      expect((await deleting).ok()).toBeTruthy()
      await expect(page.getByRole("alertdialog")).toHaveCount(0)
      await expect(page.getByTestId(`schedule-${schedule.id}`)).toHaveCount(0)
      schedules.delete(schedule.id)
      const remaining = (await (await page.request.get("/api/v1/admin/schedules")).json()).data
      expect(remaining.some((item: { id: string }) => item.id === schedule.id)).toBe(false)
      expect(remaining.find((item: { id: string }) => item.id === neighbor.id)).toMatchObject({
        id: neighbor.id,
        enabled: false,
        schedule_expression: "0 21 * * 1-5",
      })
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
        width,
      )
      await page.screenshot({
        path: testInfo.outputPath(`system-plans-${width}.png`),
        fullPage: true,
      })
    } finally {
      for (const id of schedules) {
        await page.request.patch(`/api/v1/admin/schedules/${id}`, {
          headers,
          data: { enabled: false },
        })
        const removed = await page.request.delete(`/api/v1/admin/schedules/${id}`, {
          headers,
          data: { confirmed: true },
        })
        expect.soft([200, 404]).toContain(removed.status())
      }
      for (const id of channels) {
        await page.request.patch(`/api/v1/notifications/subscriptions/${id}`, {
          headers,
          data: { enabled: false },
        })
        const removed = await page.request.delete(`/api/v1/notifications/subscriptions/${id}`, {
          headers,
          data: { confirmed: true },
        })
        expect.soft([200, 404]).toContain(removed.status())
      }
    }
  })
}

import { expect, test } from "@playwright/test"

for (const width of [1440, 360]) {
  test(`群机器人配置显隐与测试投递、系统计划删除确认 ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 })
    await page.goto("/login")
    await page.getByLabel("用户名").fill("admin")
    await page.getByLabel("密码").fill("change-this-admin-password")
    await page.getByRole("button", { name: "登录", exact: true }).click()
    await expect(page).toHaveURL(/\/$/)
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
      const name = `${label}${width}`
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
      await dialog.getByRole("button", { name: "添加渠道", exact: true }).click()
      await expect(dialog).toHaveCount(0)
      await page.getByRole("button", { name: `测试连通性 ${name}`, exact: true }).click()
      await expect(page.getByText("测试消息已发送，请检查接收端", { exact: true })).toBeVisible()
    }
    await page.screenshot({ path: testInfo.outputPath(`robots-${width}.png`), fullPage: true })
    await page.goto("/admin/schedules")
    await expect(page.getByText(/实盘分析计划随实例启停自动更新/)).toBeVisible()
    await page.getByLabel("Cron 表达式").fill("0 21 * * 1-5")
    await page.getByRole("button", { name: "创建任务", exact: true }).click()
    const row = page
      .getByRole("row")
      .filter({ has: page.getByRole("cell", { name: "0 21 * * 1-5", exact: true }) })
    await expect(row).toHaveCount(1)
    await expect(row.getByRole("button", { name: "删除定时任务", exact: true })).toHaveCount(0)
    await row.getByRole("switch").click()
    await row.getByRole("button", { name: "删除定时任务", exact: true }).click()
    await page.getByRole("alertdialog").getByRole("button", { name: "取消", exact: true }).click()
    await expect(row).toHaveCount(1)
    await row.getByRole("button", { name: "删除定时任务", exact: true }).click()
    await page
      .getByRole("alertdialog")
      .getByRole("button", { name: "确认删除定时任务", exact: true })
      .click()
    await expect(row).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    )
    await page.screenshot({
      path: testInfo.outputPath(`system-plans-${width}.png`),
      fullPage: true,
    })
  })
}

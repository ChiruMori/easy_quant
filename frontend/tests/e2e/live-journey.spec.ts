import { expect, test } from "@playwright/test"

test("通知订阅入口与真实接口可用", async ({ page }) => {
  await page.goto("/login")
  await page.getByLabel("用户名").fill("admin")
  await page.getByLabel("密码").fill("change-this-admin-password")
  await page.getByRole("button", { name: "登录", exact: true }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole("link", { name: "通知设置" })).toBeVisible()
  await page.goto("/notifications")
  await page.getByLabel("通知目标").fill("demo-topic")
  await page.getByRole("button", { name: "添加渠道" }).click()
  await expect(page.getByText("ntfy").last()).toBeVisible()
  await expect(page.getByText("***")).toBeVisible()
})

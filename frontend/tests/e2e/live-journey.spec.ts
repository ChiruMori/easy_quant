import { expect, test } from "@playwright/test"

test("通知订阅入口与真实接口可用", async ({ page }) => {
  await page.goto("/login")
  await page.getByLabel("用户名").fill("admin")
  await page.getByLabel("密码").fill("change-this-admin-password")
  await page.getByRole("button", { name: "登录", exact: true }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole("link", { name: "通知设置" })).toBeVisible()
  await page.goto("/notifications")
  await page.getByLabel("渠道名称", { exact: true }).fill("测试渠道")
  await page.getByLabel("通知目标").fill("demo-topic")
  await page.getByRole("button", { name: "添加渠道" }).click()
  await expect(page.getByRole("button", { name: "测试连通性" }).last()).toBeVisible()
  await expect(page.getByText("***").last()).toBeVisible()
  await page.getByRole("button", { name: "测试连通性" }).last().click()
  await expect(page.getByText("测试消息已发送，请检查接收端")).toBeVisible()
})

import { expect, test } from "@playwright/test"

for (const width of [1440, 360]) {
  test(`本地 Monaco 高亮、接口补全、预览与工具栏 ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 })
    const external: string[] = []
    page.on("request", (request) => {
      if (!new URL(request.url()).hostname.match(/^(127\.0\.0\.1|localhost)$/))
        external.push(request.url())
    })
    await page.route("**/api/v1/**", (route) => {
      const path = new URL(route.request().url()).pathname.replace("/api/v1", "")
      if (path === "/auth/me")
        return route.fulfill({
          json: {
            data: { user: { id: "u", username: "研究员", role: "admin", status: "active" } },
          },
        })
      if (path === "/strategy-library")
        return route.fulfill({
          json: {
            data: [
              {
                key: "context.position",
                name: "读取持仓",
                signature: "context.position(symbol)",
                description: "读取当前持仓",
                parameters: "symbol: 标的",
                output: "数量",
                example: 'context.position("000001")',
                runtime: "共享",
              },
            ],
          },
        })
      return route.fulfill({ json: { data: [] } })
    })
    await page.goto("/strategies/new")
    const editor = page.getByRole("textbox", { name: "策略代码", exact: true })
    await expect(editor).toBeVisible()
    await expect(page.locator(".monaco-editor .view-lines").first()).toContainText(
      "def before_market",
    )
    await expect
      .poll(() =>
        page
          .locator('.monaco-editor .view-lines span[class*="mtk"]')
          .evaluateAll((nodes) => new Set(nodes.map((node) => getComputedStyle(node).color)).size),
      )
      .toBeGreaterThan(1)
    await editor.focus()
    await editor.press("ControlOrMeta+A")
    await page.keyboard.insertText("context.")
    await editor.press("Control+Space")
    const suggestion = page
      .locator(".suggest-widget .monaco-list-row")
      .filter({ hasText: "position" })
      .first()
    await expect(suggestion).toBeVisible()
    await suggestion.click()
    await expect(page.locator(".monaco-editor .view-lines").first()).toContainText(
      "context.position(",
    )
    await editor.press("Escape")
    await page.getByRole("button", { name: "预览当前测试代码", exact: true }).click()
    const preview = page.getByLabel("Python 代码预览容器", { exact: true })
    await expect(preview.locator(".view-lines")).toContainText("context.position(")
    await expect(
      preview.getByRole("textbox", { name: "策略代码预览", exact: true }),
    ).toHaveAttribute("readonly", "true")
    await preview.getByRole("button", { name: "自动换行", exact: true }).click()
    await expect(preview.getByRole("button", { name: "自动换行", exact: true })).toHaveAttribute(
      "aria-pressed",
      "true",
    )
    await preview.getByRole("button", { name: "搜索代码", exact: true }).click()
    await expect(preview.locator(".find-widget")).toBeVisible()
    await preview.getByRole("button", { name: "放大代码预览", exact: true }).click()
    await expect(page.getByRole("dialog")).toContainText("策略代码预览")
    await expect(page.getByRole("dialog").locator(".view-lines")).toContainText("context.position(")
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    )
    await page.screenshot({
      path: testInfo.outputPath(`code-preview-${width}.png`),
      fullPage: true,
    })
    await page.getByRole("dialog").getByRole("button", { name: "关闭", exact: true }).click()
    expect(external).toEqual([])
  })
}

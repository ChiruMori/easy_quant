# 验证记录

- `pnpm check` 通过：Ruff、Pyright、741 项后端测试；Prettier、ESLint、55 项前端测试与生产构建。
- `uv run --project backend pre-commit run --all-files` 全部通过。
- Playwright：`portfolio-comparison.spec.ts`、`live-progressive.spec.ts`、`live-freeze-layout.spec.ts` 共 6 项通过；标记布局调整后再次执行组合图表 2 项，通过。
- 查看 1440px、360px 截图，验证持仓市值、缺行情、比例两位小数、B/S 同日分离与两种单位、跨 UTC 日期按上海归属、成交明细提示、局部估值失败恢复；页面无整体横向溢出。
- 后端离线回归覆盖完整 23 笔人工买卖（超过列表首屏）、Decimal 持仓市值、缺行情、未来行情不可见、初始持仓不生成买点与终止冻结后不再读取行情。
- 兼容限制：旧冻结快照无新字段时不读取当前行情补算，市值显示不可估值，成交点保持缺失。
- 构建仍有已有的大体积 chunk 提示，不影响构建成功。

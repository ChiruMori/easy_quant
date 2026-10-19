# 验证记录

- `pnpm --dir frontend format`、`pnpm --dir frontend lint:fix`：通过。
- `pnpm check`：通过，后端 485 项、前端 42 项测试及生产构建完成。
- `pnpm --dir frontend test:e2e tests/e2e/workspace-style.spec.ts tests/e2e/page-audit.spec.ts`：最终 8 个场景通过。
- `uv run --project backend pre-commit run --all-files`：通过。
- 桌面验证按钮位于侧栏内、内容页头无重复开关、收起后默认品牌图标、hover/focus 展开图标与提示、悬停不改变宽度、Enter/Space/Ctrl+B 切换、点击后的焦点保持以及折叠导航跳转。补齐点击后再次键盘聚焦的提示边界。
- 360px 验证抽屉入口、关闭、导航跳转及权限；全路由/指数 Tab 在 360/768/1440px 无页面级溢出。
- 已查看展开及收起 hover 截图，截图保存在本次聊天可视化产物中；只使用固定离线 fixture。更新现有 PR #16，未部署线上。

# 验证记录

- `pnpm check` 通过：459 个后端测试、37 个前端测试，Ruff、Pyright、Prettier、ESLint、TypeScript 与生产构建均通过。
- `pnpm --dir frontend exec playwright test --timeout=60000` 通过全部 10 个场景。默认 30 秒时管理员完整旅程曾超时，使用 60 秒时限重跑通过；停复牌刷新用例已同步新增二次确认步骤。
- `uv run --project backend pre-commit run --all-files` 及提交钩子通过。
- 已查看 360px 日期弹层与删除失败弹窗截图；确认日历可选、字段值更新、页面无横向溢出，关联阻止显示名称、取消无删除、删除失败可重试。
- 删除测试覆盖任意状态实盘阻止策略删除、所有权隔离、真实布尔值确认、级联清理、执行中任务阻止与回滚；SQL fake 验证结果明细与无引用快照清理、共享快照保留、提交失败回滚，以及专项外键迁移范围。测试不连接真实数据库或第三方服务。
- 本机 Docker 引擎未启动，无法在本机执行容器冒烟。Ubuntu CI 新增镜像构建与 `--network none` 运行检查，以 UID 65532 创建、写入和删除 `/app/backend/.local-data/tdx/daily` 中的临时文件。远端结果见 [PR #14 检查](https://github.com/ChiruMori/easy_quant/pull/14/checks)。
- 已同步目标主分支，修复在 `fix/resource-deletion-and-date-picker` 分支提交并推送。部署前需要先停服务、备份数据库并执行 `0012_resource_lifecycle` 迁移。

# 验收记录

策略工作台默认展示按版本分页的列表，草稿原地编辑，测试中与已实盘版本通过确认复制为新草稿。快测执行当前代码，不创建历史版本，任务结束清除临时代码。模板覆盖确认、公共库侧栏、图标 CRUD 与同义状态去重均已实现。

- `pnpm check`：485 个后端测试、42 个前端测试，格式、类型、静态检查与生产构建通过。
- `uv run --project backend pre-commit run --all-files`：全部通过。
- `pnpm --dir frontend exec playwright test --timeout=60000`：11 个场景通过，包含完整策略、快测、回测、实盘旅程及新增工作台交互。
- 已检查桌面列表、桌面编辑器和公共库侧栏、360px 编辑页及通知图标操作截图。
- 测试使用 fake、内存仓储和固定 fixture；迁移通过模拟连接验证列升级、历史状态回填、幂等及不新增外键。

部署先执行 `0013_strategy_workspace`，同时升级 API 与 worker。历史实盘的所有状态均参与回填，删除关联记录不会回退已锁定版本。草稿修订号防止过期保存；回测提交及实盘创建与状态提升均由同一事务提交。

本分支包含尚未合并的 PR #14 资源生命周期基础；新 PR 合并前需结合该依赖审阅。

已提交推送分支 `feat/strategy-workspace-lifecycle`，审阅入口：[PR #15](https://github.com/ChiruMori/easy_quant/pull/15)。

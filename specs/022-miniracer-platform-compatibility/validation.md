# 验证记录

- 根因由冻结锁文件的条件依赖及旧版官方实现确认：Linux 使用 py-mini-racer 0.6.0，无上下文管理协议；本地 Windows 使用 mini-racer 0.14.1。
- 6 项离线回归验证旧/新实现的成功、eval 失败、call 失败，确认 5000ms 超时、错误传播及新版 close。使用 fake，不打开真实引擎或网络。
- 分别用真实 Windows 0.14.1 和 Linux 容器 0.6.0 执行固定 JavaScript fixture，验证普通实例调用及返回值。Linux 容器使用 Python 3.12.12、`--network none`、只读挂载本次源码，不访问数据库。
- `pnpm check` 通过：Ruff、Pyright、441 项后端测试、32 项前端测试和生产构建。
- `pnpm test:e2e`：9 项全部通过。
- 工作流 YAML 解析验证通过：PR 触发 check，publish 仅在 master 执行。真实 Ubuntu 工作流结果以修复 PR 的 Actions 检查为准。

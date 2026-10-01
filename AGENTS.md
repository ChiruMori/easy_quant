# 开发代理协作规则

- 默认用中文与用户沟通、写项目文档和说明；代码标识符及协议名保留原文。
- 先读 `.specify/memory/constitution.md` 及当前 feature 的 `spec.md`、`plan.md`、`tasks.md`。不得扩大到高频、自动下单、公共注册或分布式架构。
- 后端专用文件必须位于 `backend/`，虚拟环境固定为 `backend/.venv`，命令使用 `uv run --project backend`。前端使用 pnpm，禁止生成 npm/yarn 锁文件。共享入口放根 `package.json` 或 `tools/`。
- 因子与策略必须分离：因子是代码内平台方法、随应用发布且无用户版本；策略可由用户编辑，每次保存产生不可变版本。
- 领域代码不得依赖 Flask、SQLAlchemy、网络、环境时间或随机全局状态。所有外部边界通过端口和适配器连接。
- 测试不得访问第三方网络、中间件或真实存储。使用 fake、内存仓储和版本化 fixture；优先覆盖时间一致性、Decimal 资金演算、幂等、权限和失败恢复。
- 修改行为时同步测试和 `docs/`。`docs/` 只写当前真实状态，未来设计留在 `specs/`。
- 不记录密码、token、邀请码、联系方式和数据源凭据；日志必须脱敏。动态策略只能在受限子进程执行。
- 编辑前端后运行 `pnpm --dir frontend format` 和 `pnpm --dir frontend lint:fix`；编辑 Python 后运行 Ruff format/check。提交前运行 `pnpm check` 和受影响的 Playwright 测试。不要修改或删除用户无关改动，不使用破坏性 Git 命令。
- 国际网络访问需要时可使用 `http://127.0.0.1:7890`，但应用和测试不得依赖代理。

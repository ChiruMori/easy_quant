# Easy Quant 易量化平台

面向少量受邀用户的日频股票研究与投资决策辅助平台。它统一采集和导入公开行情，提供平台因子、可版本化策略、可复现回测、实盘建议、通知和实际操作账本；不连接券商、不自动下单，也不承诺收益。

## 当前可用能力

- 启动时按 `backend/.env` 自动创建初始管理员；全站登录守卫、登出切换用户、管理员签发一次性邀请码和邀请注册均已接通。
- 数据管理页可真实调用 AKShare/东方财富，管理沪深京证券、交易日历、日线、估值、市值、质押和财务数据；来源随机起选、失败切换，原始响应按来源缓存。
- 管理员 CLI 可下载通达信官方沪深京全量与每日增量不复权日线；支持批量事务、检查点恢复、缺日重试和来源修订核验。定时任务页面可创建“通达信 A 股盘后增量”计划；操作见[通达信历史数据](docs/通达信历史数据.md)。
- 股票覆盖表提供完全同步、部分同步、数据不足、未同步、已更新和已过时判定，并可补齐到上一交易日或盘后今日。
- 因子目录提供 K 线、市值、5 日均线、RSI、MACD、历史预期回报和通用基本面读取能力。
- 策略工作台支持浏览器草稿、不可变版本、两个模板、盘前/盘中/盘后钩子、受限子进程和真实数据运行。
- 回测页从已保存策略版本中选择，标的由策略产生；只读取已导入日线，缺失时阻断并提示同步范围，不再生成模拟行情。记录页展示中文指标、资金曲线、成交和假设。
- 实盘从成功回测启动，worker 执行盘前信号、盘中固定频率触价监控和盘后持仓提醒；邮件/ntfy 通知与确认、拒绝、修正账本已串联。人工操作先校验资金/持仓再原子提交，支持用户隔离幂等重试及页面处理反馈。
- API 与 worker 在开发、测试部署和生产环境都连接 `EASY_QUANT_DATABASE_URL` 指向的 MariaDB，持久化身份、策略、数据、回测、实盘、通知和管理状态；运行时没有进程内存储模式。

## 快速开始

需要 Python 3.12+、uv、Node.js 22+ 和 pnpm 10。

```powershell
uv sync --project backend
pnpm install
pnpm --dir frontend install
Copy-Item backend/.env.example backend/.env
pnpm migrate
pnpm dev
```

后端位于 `http://127.0.0.1:5000`，前端位于 `http://127.0.0.1:5173`。启动前必须确保 MariaDB 可用并执行一次 `pnpm migrate`。VS Code 可直接运行“全栈开发（双端热更新）”。worker 使用 `pnpm dev:worker`。初始管理员来自 `EASY_QUANT_INITIAL_ADMIN_USERNAME`、`EASY_QUANT_INITIAL_ADMIN_PASSWORD`，首次启动前必须修改示例值。完整验证见 [quickstart](specs/001-platform-foundation/quickstart.md)。

## 质量检查与部署

```powershell
pnpm fix
pnpm check
pnpm test:e2e
pnpm hooks:install
```

`pnpm fix` 会统一执行前端 Prettier/ESLint 和后端 Ruff 自动修复；完整门禁还会执行 TypeScript、Pyright 与测试。pre-commit 会在每次提交前执行快速格式化、自动修复和类型检查。所有自动化测试离线运行，不访问真实数据库或第三方服务。单机容器部署见 [部署与运维](docs/部署与运维.md) 和 `deploy/compose.yaml`。

## 目录

- `backend/`：Python 包、后端虚拟环境、迁移、测试、OpenAPI 与镜像。
- `frontend/`：React SPA、单元测试、Playwright 验收与镜像。
- `docs/`：只描述当前真实系统的 Living Docs。
- `specs/`：需求、计划、任务、契约与验收证据。
- `tools/`：前后端共享的开发和运维脚本。

文档导航：[系统使用说明](docs/系统使用说明.md) · [系统架构](docs/系统架构.md) · [数据平台](docs/数据平台.md) · [因子与策略](docs/因子与策略.md) · [回测与实盘](docs/回测与实盘.md) · [部署与运维](docs/部署与运维.md) · [当前限制](docs/当前限制.md) · [Git 规范](docs/Git%20协作规范.md)

## 风险声明

本项目仅用于研究和辅助决策。公开数据可能延迟、缺失或错误，历史回测不代表未来表现；所有交易决定和实际操作由用户自行完成并承担风险。

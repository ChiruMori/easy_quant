# 首次验证指南

## 1. 安装与配置

```powershell
uv sync --project backend
pnpm install
pnpm --dir frontend install
Copy-Item backend/.env.example backend/.env
pnpm migrate
```

先创建可用的 MariaDB 数据库，把 `backend/.env` 中的数据库 URL、secret、credential encryption key 和初始管理员密码替换为实际配置，再执行初始结构基线。所有运行环境都使用该数据库持久化，数据库不可用时不会回退到内存。开发期不需要配置真实通知服务；公开数据与通知适配器由离线自动化测试 fake 覆盖。

## 2. 启动

运行 `pnpm dev`，另一个终端可选运行 `pnpm dev:worker`。打开 `http://127.0.0.1:5173`。系统启动时自动按 `backend/.env` 创建初始管理员，所有业务页面均要求登录；管理员可在系统管理中签发单次邀请码供普通用户注册。

## 3. 首条研究链路

1. 在“数据管理”查看数据集与股票数据覆盖；数据来源由系统自动选择并在失败时切换。
2. 使用本地 fixture 或符合模板的 CSV 完成导入预览与确认写入；确认错误行不会写入。
3. 在“因子”查看 `market.daily-bars` 和 `technical.ma` 的参数与输出说明。
4. 在“策略”从两个示例之一创建版本并运行，确认页面显示 stdout、信号或结构化错误。
5. 在“回测”选择策略版本、日期、初始资金、费用与滑点；数据不足时应看到同步指引，数据完整时可在“回测记录”查看快照身份、资金曲线、交易和中文指标。
6. 仅从成功回测开启实盘，配置测试通知订阅；生成建议后分别验证确认、拒绝和修正路径。

## 4. 离线验收

```powershell
pnpm check
pnpm test:e2e
```

预期后端 Ruff、Pyright、Pytest，前端 ESLint、TypeScript、Vitest、Vite build，以及 Chrome Playwright 场景全部通过。

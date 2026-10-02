# Implementation Plan: Easy Quant 易量化平台基础能力

**Branch**: `001-platform-foundation` | **Date**: 2026-09-29 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-platform-foundation/spec.md`

## Summary

以模块化单体实现一个前后端分离的低频股票投资辅助平台：React PC Web 通过版本化 REST API 调用 Flask 后端；MariaDB 保存业务数据、任务状态、原始响应缓存和审计信息；单机后台 worker 执行数据拉取、策略验证与运行、回测、实盘分析和通知投递。系统不引入 Redis、Celery、分布式锁、对象存储或集群调度器。

后端按领域端口与基础设施适配器分离。AKShare、东方财富、上传文件、MariaDB、邮件和 ntfy 都位于适配器边界；因子是随程序发布的只读方法目录，策略通过受控上下文调用因子。策略代码在独立子进程中运行，设置超时、输出上限并移除应用密钥环境，提供故障隔离但不宣称能对恶意代码形成安全沙箱。

## Technical Context

**Language/Version**: Python 3.12+；TypeScript 5.x；Node.js 当前维护期 LTS

**Primary Dependencies**: 后端由 uv 管理 Flask、SQLAlchemy 2、Alembic、Pydantic 2、pandas、NumPy、AKShare、httpx；前端由 pnpm 管理 React、Vite、React Router、TanStack Query、shadcn/ui、Tailwind CSS v4、CodeMirror 6、Recharts

**Storage**: 开发、测试部署和生产运行时统一使用配置的 MariaDB 保存规范化数据、压缩原始响应、应用任务与业务实体；不存在运行时易失存储配置；预训练模型权重作为只读发布文件随后端部署

**Testing**: pytest、Ruff、Pyright；Vitest、React Testing Library；Playwright 仅使用本地 fake API 或进程内测试服务，不访问第三方服务

**Target Platform**: 单个受限部署环境中的 Linux 容器或主机；开发环境支持 Windows；PC 现代浏览器

**Project Type**: 前后端分离 Web 应用，包含 API 进程和单机后台 worker 进程

**Performance Goals**: 普通查询与配置接口在规划规模内 p95 小于 500 ms；长任务在 2 秒内返回任务标识；新日线数据满足完整性条件后 10 分钟内完成启用实盘实例的分析与通知入队

**Constraints**: 最细日线；不自动下单；不做分布式和高可用；自动化测试完全离线且不依赖真实 MariaDB、ntfy、邮件或第三方 API；原始缓存不向页面暴露；同一数据集首个成功来源即结束；策略编辑无交互式调试器

**Scale/Scope**: 少量可信用户（规划上限 20 个活跃账号、10 个并发页面会话、100 个启用实盘实例）；约 10,000 个证券身份、3,000 万条日线记录的单机数据规模；并发长任务由单个 worker 限流执行

## Constitution Check

*GATE: Phase 0 开始前必须通过；Phase 1 设计完成后重新检查。*

| 宪章约束 | 计划响应 | 结果 |
| --- | --- | --- |
| 决策辅助、不直接交易 | API 和领域模型只产生建议与实际操作账本，不包含券商下单端口 | PASS |
| 建议与实际操作分离 | `Recommendation` 和 `ActualOperation` 分属不同聚合，后续实盘状态只从账本恢复 | PASS |
| 时间一致与防未来函数 | 所有因子经带 `as_of` 的 `FactorContext` 读取数据；数据网关强制 `available_at <= as_of` | PASS |
| 回测可复现 | 回测绑定应用发布、策略版本、不可变数据快照、参数、费用、滑点和随机种子 | PASS |
| 因子与策略分离 | 因子由代码注册表只读提供；只有策略具有页面管理和独立版本生命周期 | PASS |
| 契约驱动适配器 | 数据源、上传、通知、调度和存储均实现显式端口；供应商字段不进入领域层 | PASS |
| 领域核心脱离基础设施 | `domain` 与 `application` 不导入 Flask、SQLAlchemy、AKShare、httpx 或通知 SDK | PASS |
| 完全离线测试 | 端口均提供 fake/in-memory 实现；默认测试禁止网络并注入时钟与随机源 | PASS |
| 幂等与可审计 | 任务、建议、通知、确认和规范化 upsert 使用业务幂等键；状态迁移追加审计事件 | PASS |
| 安全边界 | Cookie 会话、CSRF、归属校验、密钥隔离；策略子进程不继承密钥并有超时和输出限制 | PASS |
| 技术基线 | React + shadcn/ui + Tailwind；Python + Flask + SQLAlchemy + MariaDB；ntfy 适配器 | PASS |
| 单机和简单性 | 一个数据库、一个 API、一个 worker、一个静态前端；无分布式中间件 | PASS |
| 全环境持久化 | 默认装配路径无条件创建 MariaDB 会话和 SQL 仓储；fake 仅由测试代码显式注入 | PASS |
| 中文沟通与文档 | 用户界面、Living Docs 和工程说明默认中文，代码标识及协议术语保留原文 | PASS |

**Phase 1 复查结论**: 下述模块边界、持久化和运行拓扑没有引入宪章豁免，全部门禁仍为 PASS。

## Architecture

### 1. Runtime topology

```text
PC Browser
    │ HTTPS / JSON
    ▼
React SPA ───────────────► Flask API
                              │
                              ├── application services ──► domain
                              │
                              └── MariaDB ◄────────────── Worker
                                                          │
                                                          ├── AKShare adapter
                                                          ├── EastMoney HTTP adapter
                                                          ├── strategy subprocess
                                                          ├── backtest engine
                                                          └── email / ntfy adapters
```

- SPA 与 API 分离开发，生产部署时由同一反向代理提供同源访问，简化 Cookie 与 CSRF 边界。
- API 只执行短请求：校验输入、执行业务命令、保存状态并返回结果或任务 ID。
- 单个 worker 轮询数据库中的到期任务和待执行作业；使用数据库行状态与租约避免进程重启后的重复执行。不设计多 worker 竞争或跨节点选主。
- 数据库是唯一运行时持久化服务。原始响应以压缩 BLOB 保存，避免新增对象存储；模型权重是只读部署资源，不进入用户数据管理。

### 2. Backend boundaries

后端采用模块化单体和端口/适配器结构，而不是拆分微服务：

- `domain`: 纯 Python 领域实体、值对象、状态机、财务计算和错误；禁止导入框架与 I/O 库。
- `application`: 用例编排、事务边界、端口协议、授权策略和 DTO；通过依赖注入获得时钟、随机源、仓储、数据源和通知端口。
- `infrastructure`: SQLAlchemy 仓储、MariaDB 工作单元、外部来源、原始缓存、通知、任务轮询和策略子进程。
- `api`: Flask 蓝图、认证/CSRF、请求响应 schema、错误映射和 OpenAPI 文档。
- 按业务能力再划分 `identity`、`market_data`、`factors`、`strategies`、`backtesting`、`live_tracking`、`notifications`、`scheduling` 与 `audit`，模块之间只通过应用接口或稳定领域标识通信。

### 3. Data acquisition pipeline

```text
AcquisitionCommand
    → DatasetDefinition + ordered SourceBindings
    → semantic request identity
    → fresh raw-cache lookup
    → per-source bounded retry/backoff/rate gate
    → first successful RawEnvelope
    → durable raw cache
    → dataset-specific parser/normalizer
    → validate
    → warn + upsert current normalized record
    → acquisition summary + audit events
```

设计规则：

- `DatasetDefinition` 定义数据集业务键、时间语义、内部 schema 和适用来源，不创建万能行情表。
- 首期至少落地证券列表、日线 K 线、公司资料、主要股东、概念板块和市值所需的数据契约；每类数据使用独立表或明确的类型化表组。
- `SourceAdapter` 提供 `capabilities()`、`semantic_request()`、`fetch_raw()` 与 `parse()`。来源启停由 `SourceBinding` 管理，适配器本身不决定尝试顺序。
- `SourceSelector` 使用注入的随机源为每次获取打乱已启用来源；选中来源内部有限重试，失败后遍历剩余来源。选择与失败细节写入获取运行，管理员只看结果与诊断，不配置供应商优先级。
- 语义请求身份使用规范化 JSON 后计算 SHA-256，包含来源、数据集和影响结果的业务参数；排除 UUID、防缓存时间戳和签名等瞬时参数。分页号属于单页缓存身份，批次身份另行聚合。
- 直接 HTTP 来源的 `RawEnvelope` 保存响应正文 bytes、内容类型、字符集和必要响应头；AKShare 返回的 DataFrame 在任何领域字段映射前以带 schema 的稳定表格 JSON 保存，并记录 AKShare 与可知底层提供方。
- 原始响应写入成功后才进行解析。解析失败保留原始响应和失败状态，便于发布新解析器后重新处理。
- 缓存新鲜期决定是否跳过外部请求，保留期决定何时允许清理；强制刷新只绕过读取，不删除旧任务、回测或审计事实。
- 单个来源的重试策略区分可重试错误（超时、限流、临时服务错误）与不可重试错误（参数、认证、不可解析协议）。使用注入的 `Sleeper` 和 `Clock`，测试不真实等待。
- 任一来源成功即停止，不访问后续来源，也不跨来源验证数据。分页声明数量与实际数量不符时记录警告并标记非完整结果。
- 规范化记录使用数据集业务键 upsert。重复时写入覆盖警告和审计事件；不保留用户可浏览的旧当前值。

### 4. Reproducible data snapshots

规范化记录允许覆盖，但历史回测不能随当前数据变化：

- 回测创建时，从当前规范化数据物化一个不可变的 `DataSnapshot`，保存查询范围、记录主键与内容摘要，并将实际输入序列压缩保存。
- 回测、策略输出和指标都引用快照 ID。重复运行优先读取同一快照，不重新查询“当前”数据。
- 快照内容使用规范序列化和 SHA-256 校验；同一输入可复用已有快照。
- 实盘使用最新当前数据，但每次决策保存所用数据摘要、应用发布和策略版本，以便审计。

此设计同时满足“重复数据直接覆盖”和“历史回测可复现”，不要求为所有规范化表建立复杂的双时态模型。

### 5. Factor subsystem

- 因子通过代码注册表声明稳定名称、说明、参数 schema、输入数据集、输出 schema、时间语义和调用示例。
- `FactorContext` 只暴露带 `as_of` 的类型化数据查询、已注册因子调用、时钟和确定性随机源；数据层强制过滤可获知时间。
- 基础因子包括 K 线、市值；派生因子包括均线。复杂统计或机器学习因子使用相同调用协议。
- 预训练权重位于 `backend/resources/models/`，清单记录文件摘要、兼容应用发布和因子名称；运行期只加载和推断。
- 因子无数据库管理表、独立产品版本或写操作页面。前端因子目录来自后端只读元数据端点。

### 6. Strategy lifecycle and runtime

- `StrategyDefinition` 表示用户可管理的逻辑身份；每次保存产生不可变 `StrategyVersion`，存储源代码、参数 schema、依赖因子、内容摘要和父版本。
- 预设和示例策略以种子数据创建，但与用户策略通过同一保存、验证和运行协议；用户复制示例后获得自己的定义。
- 页面使用 CodeMirror 6 提供代码编辑、语法高亮和只读示例查看，不提供断点、单步或变量监视。
- 保存前执行静态结构验证；运行前在独立 Python 子进程加载策略模板，并通过序列化的受控上下文调用因子。
- 子进程设置墙钟超时、输出字节上限和临时工作目录，不继承数据库、邮件、数据来源等密钥。Linux 部署时增加 CPU/内存限制；Windows 开发环境至少保证超时终止。
- 本项目只面向可信用户，因此该机制定位为故障与资源隔离，不是对恶意 Python 代码的强安全沙箱。任何扩大用户信任边界的需求必须重新设计执行环境。
- `StrategyRun` 分别保存返回结果、标准输出、标准错误、警告、开始/结束时间和失败分类。

### 7. Backtesting engine

- 使用事件驱动的日线循环：交易日推进 → 建立 `as_of` 上下文 → 计算因子 → 执行策略 → 形成信号 → 按成交规则撮合 → 写入组合账本 → 计算指标。
- 金额、价格和费用使用 `Decimal`；收益率和统计计算可使用 NumPy/pandas，但入账前必须执行明确舍入。
- 交易日历、停牌、涨跌停、不可成交、复权、手续费和滑点由显式策略对象提供并记录在回测配置中。
- 回测是后台任务，按阶段保存进度；失败时保留已完成阶段和诊断，不把部分结果标为成功。
- 回测创建前由 `DataReadinessService` 根据策略声明的因子和数据依赖计算所需数据集、标的与区间；任一缺口返回结构化同步建议并终止，不允许回退到合成或示例行情。
- 策略生命周期统一为 `before_market`、`on_market`、`after_market`。回测按日调用三阶段但注入禁用通知端口；实盘盘前执行一次、盘中按单机调度器配置频率刷新、盘后执行一次。
- 回测运行、快照、逐期权益、交易、指标和输出通过仓储事务写入 MariaDB；API 数值使用十进制字符串，前端集中负责中文标签和按口径格式化。

### 管理端证券数据视图

- `instruments` 保存沪深京证券基础信息；基础信息仅由管理员全量或定向刷新。
- 日线覆盖聚合按证券计算最早/最新交易日和记录数，并依据交易日历计算十年、三年和上一交易日阈值。
- 日线同步支持证券集合与日期范围；每日任务只请求上一交易日。获取运行保留随机来源尝试顺序、重试和错误摘要。
- AKShare 首期使用官方文档声明的股票列表、个股信息与历史行情能力，东方财富直接接口作为同契约备选；两者的原始响应先缓存、后归一化。

### 内部策略接入验收

- `ref/大数投资.聚宽回测.py` 仅用于列举平台接入能力与验收，不进入种子示例。
- 逐项映射其证券全集、历史 K 线、市值/估值、财务披露时点、技术指标、三阶段调度、目标仓位与实际持仓能力；缺失映射即视为平台未完成。
- 指标计算独立于策略执行，统一提供累计/年化收益、最大回撤、波动率、风险调整收益、换手、交易次数和基准对比。

### 8. Live recommendation and ledger

- `LiveInstance` 固定引用策略版本，保存初始组合、运行参数、状态和下一决策时间。
- 每次分析从不可变账本重建实际现金、持仓和成本，未处理建议绝不进入账本。
- `Recommendation` 使用 `(live_instance_id, strategy_version_id, decision_at, instrument_id, signal_key)` 唯一业务键。
- 确认、拒绝和修正采用显式状态机及乐观并发版本。确认或修正与账本写入位于同一事务；重复请求返回已存在结果。
- `PortfolioLedgerEntry` 只追加不修改；当前组合可缓存，但必须能由初始状态和账本重建并校验。

### 9. Scheduling and jobs

- `ScheduledTask` 保存任务类型、cron/固定间隔、时区、配置、启停状态和 `next_run_at`。
- `Job` 保存业务幂等键、状态、尝试次数、可运行时间、租约、输入和结果摘要。
- worker 使用数据库轮询和短租约领取任务；单机只启动一个 worker。进程崩溃后租约到期可重试，业务端仍以幂等键防止重复副作用。
- 长任务类型包括数据拉取、缓存重新解析、策略运行、回测、实盘分析和通知投递。
- 不引入通用分布式队列。若未来需要多 worker 或高可用，必须单独立项并重新评估租约、锁与任务语义。

### 10. Notifications

- `NotificationChannel` 端口首期实现 SMTP 邮件与 ntfy。
- 建议创建后按订阅生成独立 `NotificationDelivery`；幂等键为建议、订阅和渠道组合。
- worker 仅重试临时失败；永久配置错误进入失败状态并提示用户修正。
- 通知只包含必要建议摘要和回平台链接，不包含策略源码、凭据或完整账户信息。

### 11. Identity and security

- 首次初始化创建管理员并写入一次性完成标记；后续账号只能通过有期限、单次使用的邀请码创建。
- 同源部署使用服务端签名的 `HttpOnly`、`Secure`、`SameSite=Lax` Cookie 会话，并为状态变更 API 校验 CSRF token。
- 密码使用 Argon2id 哈希；每次请求检查用户启用状态。管理员权限与普通资源归属在应用服务层统一校验，不能只依赖前端隐藏入口。
- 外部凭据使用部署密钥加密后存储，日志与 API DTO 默认脱敏。策略子进程只获得计算所需数据，不获得数据库连接或环境密钥。
- 审计记录保存操作者、触发源、动作、资源、前后状态摘要、关联任务和时间，不记录密码、token 或原始敏感凭据。

### 12. API and frontend

REST API 使用 `/api/v1` 前缀，Pydantic schema 生成稳定请求/响应定义和 OpenAPI 文档。主要资源：

- `/auth`、`/invitations`、`/users`
- `/admin/datasets`、`/admin/sources`、`/admin/acquisitions`、`/admin/uploads`、`/admin/schedules`
- `/factors`（只读目录与文档）
- `/strategies`、`/strategy-versions`、`/strategy-runs`
- `/backtests`
- `/live-instances`、`/recommendations`、`/actual-operations`
- `/notification-subscriptions`、`/notification-deliveries`
- `/jobs`、`/audit-events`

前端按业务 feature 组织路由与 API hooks，不复制领域规则：

- 管理端：数据集、来源启停、拉取/上传、任务与定时任务；来源由系统随机起选。
- 用户端：概览、因子文档、策略编辑与运行、回测、实盘实例、待处理建议、通知设置。
- 使用 shadcn/ui 现有组件组合页面；表单采用 `FieldGroup`/`Field`，状态使用 `Badge`，空状态使用 `Empty`，加载使用 `Skeleton`/`Spinner`，危险确认使用 `AlertDialog`。
- shadcn 初始化后，以 `components.json` 的 `base`、别名、图标库和路径为准；添加组件前使用 CLI 查询与阅读对应文档，不手写替代已有组件。
- 数据表使用服务端分页和筛选；长任务页面通过短轮询查询任务状态，首期不引入 WebSocket。
- 数据拉取、策略单日快速测试和回测的 API 只做参数/权限校验、创建业务占位记录与 job；外部 I/O、策略子进程和回测循环全部由单 worker handler 执行。策略快速测试按选定交易日依次执行三个阶段并把阶段化结果写入 job 摘要；回测在入队时写入排队记录，worker 原位更新该记录。
- 证券覆盖查询在仓储层完成名称/代码搜索、同步状态筛选、排序和分页；单证券日线接口按日期范围查询，前端使用现有 Recharts 依赖组合 K 线图，不额外引入图表服务。
- 大范围运行结果和策略源码在 MariaDB 使用 `LONGTEXT`；不可变快照压缩后切成不超过 60 KB 的 BLOB 块，避免单条记录超过普通 `TEXT`/`BLOB` 容量。已部署数据库通过增量迁移升级。

## Persistence Design

MariaDB 表按模块加前缀或在命名中表达归属，核心表组如下：

| 模块 | 主要表 | 关键约束 |
| --- | --- | --- |
| 身份 | `users`, `invitations`, `sessions` | 用户名/邮箱唯一；邀请码摘要唯一且单次使用 |
| 数据目录 | `dataset_definitions`, `data_sources`, `source_bindings` | 同一数据集与来源绑定唯一 |
| 拉取缓存 | `acquisition_runs`, `source_attempts`, `raw_response_cache` | 来源 + 语义请求哈希 + 获取批次唯一；payload SHA-256 校验 |
| 规范化数据 | `instruments`, `daily_bars`, `company_profiles`, `shareholder_snapshots`, `concept_boards`, `instrument_concepts` | 各数据集独立业务唯一键；upsert 写审计 |
| 快照 | `data_snapshots`, `data_snapshot_chunks` | 内容哈希不可变且可复用 |
| 策略 | `strategy_definitions`, `strategy_versions`, `strategy_runs` | 定义归属用户；版本号和内容不可变 |
| 回测 | `backtest_runs`, `backtest_periods`, `simulated_trades`, `backtest_metrics` | 绑定快照和策略版本 |
| 实盘 | `live_instances`, `recommendations`, `actual_operations`, `portfolio_ledger_entries` | 建议业务键唯一；账本只追加 |
| 通知 | `notification_subscriptions`, `notification_deliveries` | 建议 + 订阅 + 渠道幂等唯一 |
| 调度 | `scheduled_tasks`, `jobs` | 任务业务键唯一；状态与租约受约束 |
| 审计 | `audit_events` | 追加式；按资源、操作者和时间索引 |

通用约定：

- 数据库时间统一保存 UTC，交易日另存市场本地日期和交易日历标识。
- 金额与价格使用显式精度 `DECIMAL`，不使用数据库浮点类型入账。
- API 使用不透明 UUID/ULID 标识；业务唯一键另设唯一索引。
- JSON 仅保存真正可扩展的配置、输入摘要和输出，不用 JSON 代替需要约束或查询的核心字段。
- 删除优先采用停用状态；不可变版本、运行、账本和审计不得物理删除。
- Alembic 当前仅提供全新数据库的 `0001_initial` 完整结构基线；应用启动不自动修改数据库结构。

## Testing Strategy

### Test layers

- **Domain unit tests**: 纯函数、金额和持仓演算、状态机、时间可见性、因子、指标、幂等键。
- **Application tests**: 使用 `InMemoryUnitOfWork`、`FakeClock`、`FakeSleeper`、`FakeSourceAdapter`、`FakeStrategyRunner` 和 `FakeNotifier` 验证完整用例。
- **Contract tests**: 对所有数据源、通知、仓储和策略运行端口运行同一套契约；AKShare 与东方财富只读取版本控制中的脱敏响应 fixture。
- **API tests**: Flask test client 显式注入离线 fake 应用容器，验证 schema、认证、CSRF、授权和错误映射；这不是可选择的运行环境。
- **Frontend tests**: Vitest/Testing Library 模拟 API；覆盖关键表单、权限状态、策略输出和建议处理。
- **Browser acceptance tests**: Playwright 连接本地 fake API，覆盖规格中的主旅程，不访问 MariaDB 或互联网。

### Mandatory offline controls

- pytest 会话默认安装网络阻断器；任何未显式 fake 的 socket 连接直接失败。
- 所有测试使用临时目录；原始响应、模型和上传样例均为小型、脱敏、版本固定 fixture。
- 不使用真实 MariaDB 或 SQLite 充当应用依赖。SQLAlchemy 仓储的结构验证通过映射检查、SQL 编译和独立适配器单元测试完成；真实 MariaDB 仅用于非默认的人工部署验收。
- 重试与调度测试注入虚拟时钟和 sleeper，不执行真实等待。
- 随机算法固定种子；依赖当前时间的逻辑只从 `Clock` 端口读取。

### Risk-prioritized suites

1. 防未来函数与数据可获知时间。
2. 组合账本、现金/持仓/费用和重复确认。
3. 原始缓存身份、新鲜期、重解析与来源切换。
4. 策略版本不可变、子进程失败/超时和输出截断。
5. 回测快照与重复运行一致性。
6. 用户资源隔离、邀请码、会话和 CSRF。
7. 建议与通知幂等、失败恢复和任务重启恢复。

覆盖率只作为遗漏线索，不设置统一百分比门槛。

## Project Structure

### Documentation (this feature)

```text
specs/001-platform-foundation/
├── spec.md              # 已批准的产品规格
├── plan.md              # 本技术实施计划
├── research.md          # 后续需要时记录影响实现的技术调研结论
├── data-model.md        # 后续细化实体字段、状态机和索引
├── quickstart.md        # 后续实现阶段补充本地启动和验证路径
├── contracts/           # 后续细化 REST、策略、因子、来源和通知契约
└── tasks.md             # 由 $speckit-tasks 生成，不在本计划中创建
```

### Source Code (repository root)

```text
backend/
├── pyproject.toml
├── alembic.ini
├── migrations/
├── resources/
│   ├── models/                 # 随发布提供的只读模型权重与清单
│   └── examples/               # 示例策略种子源文件
├── src/easy_quant/
│   ├── domain/
│   │   ├── identity/
│   │   ├── market_data/
│   │   ├── strategies/
│   │   ├── backtesting/
│   │   ├── live_tracking/
│   │   └── notifications/
│   ├── application/
│   │   ├── ports/
│   │   └── services/
│   ├── factors/
│   │   ├── registry.py
│   │   ├── market.py
│   │   ├── technical.py
│   │   ├── statistical.py
│   │   └── ml/
│   ├── infrastructure/
│   │   ├── persistence/
│   │   ├── data_sources/
│   │   │   ├── akshare/
│   │   │   └── eastmoney/
│   │   ├── imports/
│   │   ├── strategy_runtime/
│   │   ├── scheduling/
│   │   └── notifications/
│   ├── api/
│   │   ├── blueprints/
│   │   ├── schemas/
│   │   └── middleware/
│   ├── worker/
│   ├── config.py
│   └── bootstrap.py
└── tests/
    ├── contract/
    ├── application/
    ├── domain/
    ├── api/
    ├── fixtures/
    └── architecture/

frontend/
├── package.json
├── components.json
├── src/
│   ├── app/
│   │   ├── router.tsx
│   │   └── providers.tsx
│   ├── components/
│   │   └── ui/                 # shadcn CLI 管理的组件源码
│   ├── features/
│   │   ├── auth/
│   │   ├── admin-data/
│   │   ├── factors/
│   │   ├── strategies/
│   │   ├── backtests/
│   │   ├── live-tracking/
│   │   └── notifications/
│   ├── lib/
│   │   ├── api/
│   │   └── utils.ts
│   ├── test/
│   └── main.tsx
└── tests/
    └── e2e/

docs/                              # 只描述当前已实现系统的 Living Docs
tools/                             # 提交检查、fixture 校验等工程脚本
```

**Structure Decision**: 选择同一仓库中的 `backend/` 与 `frontend/` 两个独立项目。后端保持模块化单体并复用同一领域核心，API 与 worker 仅是不同入口；前端以业务 feature 组织，shadcn 组件集中在 `components/ui`。该结构满足独立开发与部署边界，同时避免在首期引入微服务。

## Implementation Sequence

1. **工程基线**：拆分 backend/frontend，配置依赖锁定、静态检查、离线测试网络阻断和应用容器。
2. **领域基础**：值对象、时钟/随机源、工作单元、审计、身份与权限。
3. **数据平台**：数据集契约、来源端口、原始缓存、规范化 upsert、上传预检、任务状态。
4. **首期来源**：东方财富直接 HTTP 适配器、AKShare 适配器、fixture 契约测试和管理员页面。
5. **因子系统**：注册表、文档元数据、K 线/均线/市值和至少一个复杂因子。
6. **策略系统**：模板、不可变版本、示例策略、子进程执行、编辑与输出页面。
7. **回测系统**：数据快照、日线事件循环、成交模型、指标与比较页面。
8. **实盘闭环**：实例、定时分析、建议、确认/拒绝/修正和账本重建。
9. **通知**：订阅、邮件/ntfy 投递、重试与状态页面。
10. **系统验收**：离线端到端场景、权限检查、恢复演练、Living Docs 与 README 同步。

每个阶段都应交付可独立运行的纵向切片及对应测试，不等待所有后端模块完成后再集中开发前端。

## Design Decisions and Trade-offs

| 决策 | 选择 | 代价与理由 |
| --- | --- | --- |
| 系统形态 | 模块化单体 | 减少部署和事务复杂度，仍以端口保持模块边界 |
| 后台执行 | MariaDB 任务表 + 单 worker | 无额外中间件；吞吐有限但满足少量用户和低频任务 |
| 原始缓存 | MariaDB 压缩 BLOB | 部署最简单；数据库体积增大，需保留期和维护任务 |
| 规范化重复 | 当前值直接 upsert + 审计 | 符合规格；历史回测另用不可变快照保障复现 |
| 来源容错 | 随机起选，来源内有限重试，再遍历剩余来源 | 不做跨来源校验，接受首个可解析成功结果 |
| 因子发布 | 随应用代码发布 | 无页面管理和独立版本复杂度；升级由应用发布承担 |
| 策略执行 | 独立子进程 | 提供超时和故障隔离；不是恶意代码安全沙箱 |
| API 状态更新 | 短轮询 | 实现简单且适合低频任务；实时性低于 WebSocket |
| 前端组件 | shadcn/ui 源码组件 | 可控且易组合；需遵守项目 preset 和组件更新流程 |
| 数据库测试 | in-memory 端口实现 | 满足完全离线和无真实存储要求；生产方言需部署验收补足 |

## Risks and Mitigations

- **公开接口不稳定或协议变化**：保留转换前原始响应、适配器契约 fixture、可见解析失败和缓存重处理。
- **AKShare 隐藏底层来源差异**：同时记录访问适配器与可知底层提供方；不假设不同 AKShare 方法具有相同协议。
- **规范化覆盖破坏复现**：回测启动时物化不可变数据快照，结果固定引用快照。
- **策略耗尽资源**：子进程超时、输出截断、并发上限和 Linux 资源限制；只允许可信受邀用户。
- **单 worker 阻塞**：长任务分阶段、可取消、按类型设置超时；首期接受串行或小并发，避免提前分布式化。
- **MariaDB BLOB 增长**：按来源/数据集配置保留期、压缩、摘要去重和后台清理；快照与审计按治理策略单独保留。
- **邮件或 ntfy 重复投递**：投递幂等键、状态机和临时失败重试；不把送达等同于用户操作。
- **SQLite 与 MariaDB 行为差异**：不以 SQLite 模拟生产数据库；使用 SQL 编译检查并在部署验收中验证迁移。

## Complexity Tracking

无宪章违规或需要豁免的额外复杂度。独立 worker、策略子进程和不可变回测快照分别由长任务响应、策略故障隔离和覆盖数据下的可复现性直接要求，不引入分布式基础设施。

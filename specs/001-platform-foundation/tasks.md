---
description: "Easy Quant 易量化平台基础能力的依赖有序实施任务"
---

# Tasks: Easy Quant 易量化平台基础能力

**Input**: `/specs/001-platform-foundation/spec.md` 与 `/specs/001-platform-foundation/plan.md`

**Tests**: 规格和宪章明确要求风险导向的离线自动化测试，因此每个用户故事均包含测试任务。测试与实现可以同步推进，不强制形式化测试先行；故事完成前相关测试必须通过。

**Organization**: 任务按 Setup、阻塞性基础设施、七个优先级用户故事和最终收尾组织。每个任务均给出目标文件路径；标记 `[P]` 的任务在其依赖已满足且不修改相同文件时可并行。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可以与同阶段其他已标记任务并行，前提是不共享待修改文件。
- **[US1]`–`[US7]**: 对应规格中的用户故事。
- 未标故事的任务为共享基础设施或跨故事工作。

## Phase 1: Setup（工程与设计基线）

**Purpose**: 建立前后端项目、明确契约并配置完全离线的质量工具。

- [x] T001 将计划中的实体、关系、唯一键、状态机和索引细化到 `specs/001-platform-foundation/data-model.md`
- [x] T002 [P] 定义 `/api/v1` 的资源、分页、错误信封、认证和幂等请求约定到 `specs/001-platform-foundation/contracts/http-api.yaml`
- [x] T003 [P] 定义数据来源、因子、策略运行、通知和时钟端口契约到 `specs/001-platform-foundation/contracts/internal-ports.md`
- [x] T004 创建 `backend/`、`backend/src/easy_quant/`、`backend/tests/`、`frontend/`、`docs/` 和 `tools/` 的计划目录骨架并迁移根入口到 `backend/src/easy_quant/`
- [x] T005 配置根 `pyproject.toml` 为 uv workspace，并在 `backend/pyproject.toml` 声明 Flask、SQLAlchemy、Alembic、Pydantic、pandas、NumPy、AKShare、httpx、认证和开发依赖
- [x] T006 [P] 初始化 `frontend/package.json`、`frontend/vite.config.ts`、`frontend/tsconfig.json` 和 `frontend/src/main.tsx` 的 React + TypeScript + Vite 工程
- [x] T007 [P] 使用项目包管理器初始化 shadcn/ui，并提交 `frontend/components.json`、`frontend/src/index.css` 与 `frontend/src/lib/utils.ts`
- [x] T008 [P] 配置 Tailwind CSS v4、Vitest、Testing Library 和类型检查脚本到 `frontend/package.json`、`frontend/vite.config.ts` 与 `frontend/src/test/setup.ts`
- [x] T009 [P] 配置 Ruff、Pyright、pytest、覆盖率诊断和测试标记到 `backend/pyproject.toml` 与 `backend/tests/conftest.py`
- [x] T010 在 `backend/tests/conftest.py` 实现默认网络阻断、临时目录、固定时钟和固定随机种子 fixture
- [x] T011 [P] 添加环境配置样例和敏感项说明到 `.env.example` 与 `backend/src/easy_quant/config.py`
- [x] T012 [P] 添加统一开发命令到 `tools/dev.ps1`、`tools/check.ps1` 与 `frontend/package.json`，覆盖格式化、静态检查和离线测试
- [x] T013 添加最小后端导入测试和前端渲染测试到 `backend/tests/test_bootstrap.py` 与 `frontend/src/app/app.test.tsx`

**Checkpoint**: 两个项目均可安装、静态检查和运行空测试套件；设计契约路径已建立。

---

## Phase 2: Foundational（阻塞性共享能力）

**Purpose**: 实现所有用户故事共同依赖的领域类型、端口、认证、任务、审计、API 和前端壳层。

**⚠️ CRITICAL**: 本阶段完成前不得开始合并任何用户故事实现。

- [x] T014 [P] 实现 ID、UTC 时间、交易日、金额、价格、数量和百分比值对象到 `backend/src/easy_quant/domain/shared/value_objects.py`
- [x] T015 [P] 实现领域错误、应用错误与错误代码到 `backend/src/easy_quant/domain/shared/errors.py` 和 `backend/src/easy_quant/application/errors.py`
- [x] T016 [P] 定义 `Clock`、`Sleeper`、`IdGenerator`、`UnitOfWork`、仓储和事件发布端口到 `backend/src/easy_quant/application/ports/core.py`
- [x] T017 [P] 实现固定时钟、虚拟 sleeper、确定性 ID 和 in-memory 仓储基础类到 `backend/tests/fakes/core.py`
- [x] T018 创建 SQLAlchemy declarative base、命名约定、UTC/Decimal 类型与 session factory 到 `backend/src/easy_quant/infrastructure/persistence/base.py` 和 `backend/src/easy_quant/infrastructure/persistence/session.py`
- [x] T019 配置 Alembic 环境与迁移约定到 `backend/alembic.ini`、`backend/migrations/env.py` 和 `backend/migrations/script.py.mako`
- [x] T020 [P] 实现 `AuditEvent` 领域模型和审计端口到 `backend/src/easy_quant/domain/audit/entities.py` 与 `backend/src/easy_quant/application/ports/audit.py`
- [x] T021 实现审计 SQLAlchemy 模型、仓储并纳入 `backend/migrations/versions/0001_initial.py` 初始结构基线
- [x] T022 [P] 实现 `Job`、`ScheduledTask`、状态机、租约和业务幂等键到 `backend/src/easy_quant/domain/scheduling/entities.py`
- [x] T023 定义任务仓储和 handler registry 到 `backend/src/easy_quant/application/ports/jobs.py` 与 `backend/src/easy_quant/worker/registry.py`
- [x] T024 实现单 worker 的领取、续租、完成、失败和租约恢复循环到 `backend/src/easy_quant/worker/runner.py`
- [x] T025 [P] 实现 worker 重启、租约到期和重复业务键的离线测试到 `backend/tests/application/test_job_runner.py`
- [x] T026 实现 Flask app factory、依赖容器和配置装配到 `backend/src/easy_quant/api/app.py`、`backend/src/easy_quant/bootstrap.py` 与 `backend/src/easy_quant/api/dependencies.py`
- [x] T027 [P] 实现统一 JSON 响应、错误信封、请求 ID 和安全日志中间件到 `backend/src/easy_quant/api/responses.py`、`backend/src/easy_quant/api/errors.py` 与 `backend/src/easy_quant/api/middleware/request_context.py`
- [x] T028 [P] 实现 `User`、`Invitation`、角色、状态和会话领域模型到 `backend/src/easy_quant/domain/identity/entities.py`
- [x] T029 实现 Argon2id 密码服务、Cookie 会话、CSRF 和用户状态校验到 `backend/src/easy_quant/application/services/authentication.py` 与 `backend/src/easy_quant/api/middleware/auth.py`
- [x] T030 实现用户、邀请和会话持久化并纳入 `backend/migrations/versions/0001_initial.py` 初始结构基线
- [x] T031 实现一次性系统初始化、登录、登出和当前用户 API 到 `backend/src/easy_quant/api/blueprints/auth.py` 与 `backend/src/easy_quant/api/schemas/auth.py`
- [x] T032 [P] 添加身份、CSRF、停用用户和初始化幂等性的离线 API 测试到 `backend/tests/api/test_auth.py`
- [x] T033 [P] 实现前端类型化 API client、错误解析和 CSRF 注入到 `frontend/src/lib/api/client.ts` 与 `frontend/src/lib/api/types.ts`
- [x] T034 实现 React providers、路由、认证状态和 PC 应用壳层到 `frontend/src/app/providers.tsx`、`frontend/src/app/router.tsx` 与 `frontend/src/app/layout.tsx`
- [x] T035 [P] 使用 shadcn `Sidebar`、`Breadcrumb`、`Alert`、`Skeleton` 与 `Empty` 组合共享布局和状态组件到 `frontend/src/components/app-shell/`
- [x] T036 [P] 添加领域层不得导入 Flask、SQLAlchemy、AKShare、httpx 的架构测试到 `backend/tests/architecture/test_layer_boundaries.py`

**Checkpoint**: API、worker、认证、审计和前端壳层可在 fake/in-memory 基础设施上运行，后续故事拥有共同端口和质量门禁。

---

## Phase 3: User Story 1 — 管理并获取平台行情数据（Priority: P1）🎯 MVP

**Goal**: 管理员能配置 AKShare/东方财富来源，按需、批量、定时或上传获取数据；系统支持原始缓存、重试、来源切换、分页诊断、分类规范化和重复覆盖。

**Independent Test**: 使用固定响应 fixture 和 fake 来源执行缓存命中、过期刷新、三次重试、A 失败 B 成功、分页数量不匹配、上传预检和重复覆盖，全程外部调用为零。

### Tests for User Story 1

- [x] T037 [P] [US1] 编写语义缓存键、新鲜期、强制刷新、损坏缓存和重新解析测试到 `backend/tests/domain/market_data/test_raw_cache_policy.py`
- [x] T038 [P] [US1] 编写来源内重试、退避、首个成功停止和全部失败汇总测试到 `backend/tests/application/test_acquisition_service.py`
- [x] T039 [P] [US1] 编写分页数量不匹配、部分成功和实际覆盖范围测试到 `backend/tests/contract/data_sources/test_pagination_contract.py`
- [x] T040 [P] [US1] 编写上传模板、逐行错误、重复覆盖和原子导入测试到 `backend/tests/application/test_import_service.py`
- [x] T041 [P] [US1] 建立脱敏的 AKShare 与东方财富响应 fixture 到 `backend/tests/fixtures/data_sources/akshare/` 和 `backend/tests/fixtures/data_sources/eastmoney/`

### Implementation for User Story 1

- [x] T042 [P] [US1] 实现 `DatasetDefinition`、`SourceBinding`、`SemanticRequest`、`RawEnvelope`、`AcquisitionRun` 和来源尝试状态到 `backend/src/easy_quant/domain/market_data/entities.py`
- [x] T043 [P] [US1] 定义数据来源、原始缓存、规范化仓储、上传读取和重试策略端口到 `backend/src/easy_quant/application/ports/market_data.py`
- [x] T044 [US1] 实现规范 JSON 与 SHA-256 语义请求身份，排除时间戳、UUID、签名等瞬时参数到 `backend/src/easy_quant/domain/market_data/request_identity.py`
- [x] T045 [P] [US1] 实现证券列表、日线 K 线、公司资料、股东、概念板块和市值的 Pydantic 内部契约到 `backend/src/easy_quant/domain/market_data/schemas/`
- [x] T046 [US1] 实现来源随机起选、缓存读取、有限重试、退避、频率门、切换与首个成功停止的获取服务到 `backend/src/easy_quant/application/services/acquisition.py`
- [x] T047 [US1] 实现 gzip 压缩、payload SHA-256 校验和转换前写入的原始缓存仓储到 `backend/src/easy_quant/infrastructure/persistence/repositories/raw_cache.py`
- [x] T048 [P] [US1] 实现数据目录、来源、绑定、获取任务、来源尝试与原始缓存 SQLAlchemy 模型到 `backend/src/easy_quant/infrastructure/persistence/models/market_data_catalog.py`
- [x] T049 [P] [US1] 实现各规范化数据集 SQLAlchemy 模型和业务唯一键到 `backend/src/easy_quant/infrastructure/persistence/models/market_data_records.py`
- [x] T050 [US1] 将数据目录、原始缓存和规范化数据纳入 `backend/migrations/versions/0001_initial.py` 初始结构基线
- [x] T051 [US1] 实现规范化 upsert、覆盖警告和审计事件到 `backend/src/easy_quant/application/services/normalization.py` 与 `backend/src/easy_quant/infrastructure/persistence/repositories/market_data.py`
- [x] T052 [P] [US1] 实现东方财富 HTTP client、股票列表分页和公司资料适配器到 `backend/src/easy_quant/infrastructure/data_sources/eastmoney/client.py` 与 `backend/src/easy_quant/infrastructure/data_sources/eastmoney/adapters.py`
- [x] T053 [P] [US1] 实现 AKShare 返回值的转换前稳定表格序列化、股东和概念板块适配器到 `backend/src/easy_quant/infrastructure/data_sources/akshare/serialization.py` 与 `backend/src/easy_quant/infrastructure/data_sources/akshare/adapters.py`
- [x] T054 [US1] 对 AKShare 和东方财富运行统一离线来源契约测试到 `backend/tests/contract/data_sources/test_akshare.py` 与 `backend/tests/contract/data_sources/test_eastmoney.py`
- [x] T055 [P] [US1] 定义首期上传模板、示例和错误 schema 到 `backend/resources/import_templates/daily-bars-v1.json` 与 `backend/tests/fixtures/imports/`
- [x] T056 [US1] 实现上传预检、确认导入和错误报告服务到 `backend/src/easy_quant/application/services/imports.py` 与 `backend/src/easy_quant/infrastructure/imports/csv_reader.py`
- [x] T057 [US1] 注册数据拉取、缓存重解析和上传导入 worker handlers 到 `backend/src/easy_quant/worker/handlers/market_data.py`
- [x] T058 [US1] 实现数据集、来源启停、拉取、强制刷新、上传预检和任务查询 API 到 `backend/src/easy_quant/api/blueprints/admin_market_data.py` 与 `backend/src/easy_quant/api/schemas/market_data.py`
- [x] T059 [P] [US1] 实现前端数据集、来源、获取任务和上传 API hooks 到 `frontend/src/features/admin-data/api.ts` 与 `frontend/src/features/admin-data/types.ts`
- [x] T060 [US1] 实现管理员数据集与来源启停页面到 `frontend/src/features/admin-data/pages/datasets-page.tsx` 与 `frontend/src/features/admin-data/components/source-toggle-form.tsx`
- [x] T061 [P] [US1] 实现拉取任务、强制刷新、分页诊断和状态详情页面到 `frontend/src/features/admin-data/pages/acquisitions-page.tsx`
- [x] T062 [P] [US1] 实现上传预检、错误表格和确认导入页面到 `frontend/src/features/admin-data/pages/import-page.tsx`
- [x] T063 [US1] 添加管理员数据 API 授权、原始缓存不可见和错误信封测试到 `backend/tests/api/test_admin_market_data.py`
- [x] T064 [US1] 添加数据管理主旅程的前端测试到 `frontend/src/features/admin-data/admin-data.test.tsx`

**Checkpoint**: 管理员可在 PC 页面独立完成数据来源配置、获取、上传和诊断；US1 的所有测试无需网络或真实数据库。

---

## Phase 4: User Story 2 — 在策略中使用平台因子（Priority: P2）

**Goal**: 平台随程序提供只读因子目录、文档和可复现调用能力，不提供因子或模型管理页面。

**Independent Test**: 在固定数据和 `as_of` 下分别调用 K 线、均线、市值及复杂分析因子，验证输出、文档、可复现性和未来数据不可见。

### Tests for User Story 2

- [x] T065 [P] [US2] 编写因子注册、参数校验、未知因子和文档完整性测试到 `backend/tests/domain/factors/test_registry.py`
- [x] T066 [P] [US2] 编写 `available_at <= as_of`、固定随机源和重复调用一致性测试到 `backend/tests/domain/factors/test_context.py`
- [x] T067 [P] [US2] 编写模型权重摘要、缺失权重和只执行推断测试到 `backend/tests/domain/factors/test_ml_factor.py`

### Implementation for User Story 2

- [x] T068 [US2] 实现因子描述、参数/输出 schema、调用协议和只读注册表到 `backend/src/easy_quant/factors/registry.py` 与 `backend/src/easy_quant/factors/types.py`
- [x] T069 [US2] 实现带 `as_of` 强制过滤的数据网关和 `FactorContext` 到 `backend/src/easy_quant/factors/context.py`
- [x] T070 [P] [US2] 实现 K 线和市值基础因子到 `backend/src/easy_quant/factors/market.py`
- [x] T071 [P] [US2] 实现均线技术因子及无足够窗口时的明确结果到 `backend/src/easy_quant/factors/technical.py`
- [x] T072 [P] [US2] 实现至少一个统计或预训练模型推断因子到 `backend/src/easy_quant/factors/statistical.py` 或 `backend/src/easy_quant/factors/ml/prediction.py`
- [x] T073 [US2] 添加模型权重清单、摘要校验和加载器到 `backend/resources/models/manifest.json` 与 `backend/src/easy_quant/factors/ml/loader.py`
- [x] T074 [US2] 实现只读因子目录和单因子文档 API 到 `backend/src/easy_quant/api/blueprints/factors.py` 与 `backend/src/easy_quant/api/schemas/factors.py`
- [x] T075 [P] [US2] 实现前端因子目录、搜索和文档页面到 `frontend/src/features/factors/pages/factor-catalog-page.tsx` 与 `frontend/src/features/factors/pages/factor-detail-page.tsx`
- [x] T076 [US2] 添加因子页面无管理入口和文档示例展示测试到 `frontend/src/features/factors/factors.test.tsx`

**Checkpoint**: 因子可被独立调用和查阅，且页面中不存在新增、编辑、训练、上传、删除或发布入口。

---

## Phase 5: User Story 3 — 在页面创建和运行策略（Priority: P3）

**Goal**: 用户可在页面创建、编辑、版本化、验证和运行策略，查看输出，并使用至少两个示例策略。

**Independent Test**: 有效用户策略与两个示例策略通过相同契约运行；无效入口、未知因子、非法信号、超时和过量输出均展示确定错误。

### Tests for User Story 3

- [x] T077 [P] [US3] 编写策略模板、参数 schema、信号和因子依赖契约测试到 `backend/tests/contract/strategies/test_strategy_contract.py`
- [x] T078 [P] [US3] 编写版本不可变、父版本和内容摘要测试到 `backend/tests/application/test_strategy_versions.py`
- [x] T079 [P] [US3] 编写子进程成功、异常、超时、输出截断和密钥环境移除测试到 `backend/tests/infrastructure/test_strategy_runner.py`

### Implementation for User Story 3

- [x] T080 [P] [US3] 实现 `StrategyDefinition`、`StrategyVersion`、`StrategyRun`、信号和运行状态到 `backend/src/easy_quant/domain/strategies/entities.py`
- [x] T081 [P] [US3] 定义策略仓储、验证器与运行器端口到 `backend/src/easy_quant/application/ports/strategies.py`
- [x] T082 [US3] 实现策略静态结构、模板入口、参数、因子引用和信号输出验证到 `backend/src/easy_quant/application/services/strategy_validation.py`
- [x] T083 [US3] 实现策略定义与不可变版本保存服务到 `backend/src/easy_quant/application/services/strategies.py`
- [x] T084 [US3] 实现策略 SQLAlchemy 模型、仓储并纳入 `backend/migrations/versions/0001_initial.py` 初始结构基线
- [x] T085 [US3] 定义父子进程 JSON 协议、受控策略上下文和结果信封到 `backend/src/easy_quant/infrastructure/strategy_runtime/protocol.py`
- [x] T086 [US3] 实现跨平台策略子进程、墙钟超时、输出上限、临时目录和环境清理到 `backend/src/easy_quant/infrastructure/strategy_runtime/runner.py` 与 `backend/src/easy_quant/infrastructure/strategy_runtime/child.py`
- [x] T087 [US3] 实现策略上下文到因子注册表的只读桥接到 `backend/src/easy_quant/infrastructure/strategy_runtime/factor_bridge.py`
- [x] T088 [P] [US3] 编写正预期示例策略到 `backend/resources/examples/positive-expectation.py`
- [x] T089 [P] [US3] 编写第二个示例策略到 `backend/resources/examples/moving-average.py`
- [x] T090 [US3] 实现示例策略幂等种子加载到 `backend/src/easy_quant/infrastructure/persistence/seeds/strategies.py`
- [x] T091 [US3] 注册策略验证和运行 worker handler 到 `backend/src/easy_quant/worker/handlers/strategies.py`
- [x] T092 [US3] 实现策略 CRUD、版本、复制示例、验证、运行和输出 API 到 `backend/src/easy_quant/api/blueprints/strategies.py` 与 `backend/src/easy_quant/api/schemas/strategies.py`
- [x] T093 [P] [US3] 实现策略 API hooks 和类型到 `frontend/src/features/strategies/api.ts` 与 `frontend/src/features/strategies/types.ts`
- [x] T094 [US3] 使用 CodeMirror 6 实现策略列表、编辑、版本和复制示例页面到 `frontend/src/features/strategies/pages/` 与 `frontend/src/features/strategies/components/strategy-editor.tsx`
- [x] T095 [P] [US3] 实现运行结果、标准输出、警告、错误和任务状态页面到 `frontend/src/features/strategies/pages/strategy-run-page.tsx`
- [x] T096 [US3] 添加策略 API、页面工作流和“无调试控件”测试到 `backend/tests/api/test_strategies.py` 与 `frontend/src/features/strategies/strategies.test.tsx`

**Checkpoint**: 用户可完整管理和运行策略，历史版本保持不变，两个示例策略可复制并运行。

---

## Phase 6: User Story 4 — 执行并比较可复现回测（Priority: P4）

**Goal**: 用户可用不可变策略版本和数据快照执行日线回测，查看并比较统一口径结果。

**Independent Test**: 固定输入重复 10 次得到相同因子、信号、交易、轨迹和指标；未来数据访问为零，当前数据覆盖不改变历史回测。

### Tests for User Story 4

- [x] T097 [P] [US4] 编写未来数据隔离、交易日顺序和因子 `as_of` 测试到 `backend/tests/domain/backtesting/test_temporal_integrity.py`
- [x] T098 [P] [US4] 编写现金、持仓、费用、滑点、停牌和不可成交测试到 `backend/tests/domain/backtesting/test_execution.py`
- [x] T099 [P] [US4] 编写十次重复运行、快照复用和当前数据覆盖不影响结果测试到 `backend/tests/application/test_backtest_reproducibility.py`

### Implementation for User Story 4

- [x] T100 [P] [US4] 实现回测配置、运行、周期、模拟交易、组合和指标领域模型到 `backend/src/easy_quant/domain/backtesting/entities.py`
- [x] T101 [P] [US4] 实现 `DataSnapshot`、规范序列化、分块和内容摘要到 `backend/src/easy_quant/domain/backtesting/snapshots.py`
- [x] T102 [US4] 实现快照构建与内容复用服务到 `backend/src/easy_quant/application/services/data_snapshots.py`
- [x] T103 [US4] 实现数据快照、回测、周期、交易和指标 SQLAlchemy 模型并纳入 `backend/migrations/versions/0001_initial.py` 初始结构基线
- [x] T104 [US4] 实现交易日历、撮合、停牌、费用、滑点与 Decimal 舍入策略到 `backend/src/easy_quant/domain/backtesting/execution.py`
- [x] T105 [US4] 实现日线事件循环和策略运行集成到 `backend/src/easy_quant/domain/backtesting/engine.py`
- [x] T106 [P] [US4] 实现累计/年化收益、最大回撤、波动率、风险调整收益、换手和基准指标到 `backend/src/easy_quant/domain/backtesting/metrics.py`
- [x] T107 [US4] 实现回测应用服务和阶段进度保存到 `backend/src/easy_quant/application/services/backtests.py`
- [x] T108 [US4] 注册回测 worker handler 和取消检查到 `backend/src/easy_quant/worker/handlers/backtests.py`
- [x] T109 [US4] 实现回测创建、任务状态、详情和比较 API 到 `backend/src/easy_quant/api/blueprints/backtests.py` 与 `backend/src/easy_quant/api/schemas/backtests.py`
- [x] T110 [P] [US4] 实现回测配置表单和 API hooks 到 `frontend/src/features/backtests/pages/backtest-create-page.tsx` 与 `frontend/src/features/backtests/api.ts`
- [x] T111 [P] [US4] 实现回测进度、指标、权益曲线、交易表和假设披露页面到 `frontend/src/features/backtests/pages/backtest-detail-page.tsx`
- [x] T112 [P] [US4] 实现双回测配置与指标比较页面到 `frontend/src/features/backtests/pages/backtest-compare-page.tsx`
- [x] T113 [US4] 添加回测 API 和前端验收测试到 `backend/tests/api/test_backtests.py` 与 `frontend/src/features/backtests/backtests.test.tsx`

**Checkpoint**: 单个回测和双回测比较均可独立使用；结果可追溯到策略版本、应用发布和不可变数据快照。

---

## Phase 7: User Story 5 — 启动实盘建议跟踪（Priority: P5）

**Goal**: 用户可从成功回测启动实盘实例，系统按计划获取数据、运行策略、产生唯一建议并通过邮件/ntfy 通知。

**Independent Test**: 用固定时钟推进多个交易日，重复调度不重复创建建议；一个通知渠道失败不影响另一个渠道。

### Tests for User Story 5

- [x] T114 [P] [US5] 编写实盘启动、暂停、终止和下一决策时间测试到 `backend/tests/application/test_live_instances.py`
- [x] T115 [P] [US5] 编写建议业务键、重复调度和待处理建议不入账测试到 `backend/tests/domain/live_tracking/test_recommendations.py`
- [x] T116 [P] [US5] 编写邮件/ntfy 成功、临时失败、永久失败和投递幂等契约测试到 `backend/tests/contract/notifications/`

### Implementation for User Story 5

- [x] T117 [P] [US5] 实现 `LiveInstance`、`Recommendation`、状态机和建议业务键到 `backend/src/easy_quant/domain/live_tracking/entities.py`
- [x] T118 [P] [US5] 实现订阅、投递、渠道状态和通知端口到 `backend/src/easy_quant/domain/notifications/entities.py` 与 `backend/src/easy_quant/application/ports/notifications.py`
- [x] T119 [US5] 实现实盘实例、建议、订阅和投递 SQLAlchemy 模型并纳入 `backend/migrations/versions/0001_initial.py` 初始结构基线
- [x] T120 [US5] 实现从成功回测创建、暂停和终止实盘实例的应用服务到 `backend/src/easy_quant/application/services/live_instances.py`
- [x] T121 [US5] 实现新决策时点的数据获取、策略执行和唯一建议生成到 `backend/src/easy_quant/application/services/live_analysis.py`
- [x] T122 [P] [US5] 实现 SMTP 邮件适配器到 `backend/src/easy_quant/infrastructure/notifications/email.py`
- [x] T123 [P] [US5] 实现 ntfy 适配器到 `backend/src/easy_quant/infrastructure/notifications/ntfy.py`
- [x] T124 [US5] 实现按建议与订阅创建投递、分类重试和状态更新到 `backend/src/easy_quant/application/services/notification_delivery.py`
- [x] T125 [US5] 注册实盘分析和通知投递 worker handlers 到 `backend/src/easy_quant/worker/handlers/live_tracking.py` 与 `backend/src/easy_quant/worker/handlers/notifications.py`
- [x] T126 [US5] 实现实盘实例、建议列表、订阅和投递状态 API 到 `backend/src/easy_quant/api/blueprints/live_tracking.py` 与 `backend/src/easy_quant/api/blueprints/notifications.py`
- [x] T127 [P] [US5] 实现实盘与通知 API hooks 到 `frontend/src/features/live-tracking/api.ts` 与 `frontend/src/features/notifications/api.ts`
- [x] T128 [US5] 实现从回测启动、实盘列表和实例详情页面到 `frontend/src/features/live-tracking/pages/`
- [x] T129 [P] [US5] 实现通知渠道配置和投递状态页面到 `frontend/src/features/notifications/pages/notification-settings-page.tsx`
- [x] T130 [US5] 添加实盘分析、渠道隔离和通知幂等 API/前端测试到 `backend/tests/api/test_live_tracking.py` 与 `frontend/src/features/live-tracking/live-tracking.test.tsx`

**Checkpoint**: 实盘实例能按交易日生成唯一建议并通过启用渠道投递；系统仍未包含任何自动下单能力。

---

## Phase 8: User Story 6 — 确认或修正实际操作（Priority: P6）

**Goal**: 用户可确认、拒绝或修正建议；实际组合完全由不可变账本决定，重复或并发请求不重复入账。

**Independent Test**: 分别执行确认、拒绝和修正，再推进下一决策日；后续现金、持仓和成本与各自账本完全一致。

### Tests for User Story 6

- [x] T131 [P] [US6] 编写确认、拒绝、修正、非法负现金和非法负持仓状态机测试到 `backend/tests/domain/live_tracking/test_actual_operations.py`
- [x] T132 [P] [US6] 编写十次重复请求、乐观并发和账本重建一致性测试到 `backend/tests/application/test_recommendation_actions.py`

### Implementation for User Story 6

- [x] T133 [P] [US6] 实现 `ActualOperation`、`PortfolioLedgerEntry`、持仓成本和账本重建到 `backend/src/easy_quant/domain/live_tracking/ledger.py`
- [x] T134 [US6] 添加实际操作和账本 SQLAlchemy 模型并纳入 `backend/migrations/versions/0001_initial.py` 初始结构基线
- [x] T135 [US6] 实现确认、拒绝、修正、业务幂等和乐观并发应用服务到 `backend/src/easy_quant/application/services/recommendation_actions.py`
- [x] T136 [US6] 在同一工作单元内实现建议状态迁移、实际操作和账本追加到 `backend/src/easy_quant/infrastructure/persistence/repositories/live_tracking.py`
- [x] T137 [US6] 将实盘分析的组合输入切换为账本重建结果到 `backend/src/easy_quant/application/services/live_analysis.py`
- [x] T138 [US6] 实现建议确认、拒绝、修正和组合账本 API 到 `backend/src/easy_quant/api/blueprints/recommendations.py` 与 `backend/src/easy_quant/api/schemas/recommendations.py`
- [x] T139 [US6] 使用 shadcn `AlertDialog`、`FieldGroup` 和表格实现建议处理与实际成交表单到 `frontend/src/features/live-tracking/components/recommendation-actions.tsx`
- [x] T140 [P] [US6] 实现组合现金、持仓、成本和账本页面到 `frontend/src/features/live-tracking/pages/portfolio-page.tsx`
- [x] T141 [US6] 添加建议处理 API、表单验证和下一日状态验收测试到 `backend/tests/api/test_recommendation_actions.py` 与 `frontend/src/features/live-tracking/recommendation-actions.test.tsx`

**Checkpoint**: 三种人工反馈路径均可独立验证，所有后续分析只使用实际账本状态。

---

## Phase 9: User Story 7 — 管理平台与受控用户（Priority: P7）

**Goal**: 管理员可管理邀请码、用户、全平台数据和定时任务；普通用户只能访问自己的私有资源。

**Independent Test**: 用管理员和两个普通用户验证一次性初始化、邀请码、来源/任务管理、跨用户拒绝及停用后的行为。

### Tests for User Story 7

- [x] T142 [P] [US7] 编写邀请码过期/单次使用、用户停用和管理员权限测试到 `backend/tests/application/test_identity_admin.py`
- [x] T143 [P] [US7] 编写所有私有核心实体的跨用户读取/修改参数化测试到 `backend/tests/api/test_resource_ownership.py`
- [x] T144 [P] [US7] 编写定时任务启停、到期计算、时区和历史运行保留测试到 `backend/tests/application/test_scheduled_tasks.py`

### Implementation for User Story 7

- [x] T145 [US7] 实现邀请签发、接受、用户列表、角色和停用服务到 `backend/src/easy_quant/application/services/identity_admin.py`
- [x] T146 [US7] 实现管理员邀请和用户管理 API 到 `backend/src/easy_quant/api/blueprints/admin_users.py` 与 `backend/src/easy_quant/api/schemas/admin_users.py`
- [x] T147 [US7] 实现 cron/固定间隔、时区、下一次运行和启停服务到 `backend/src/easy_quant/application/services/scheduled_tasks.py`
- [x] T148 [US7] 实现任务与定时任务 SQLAlchemy 仓储并纳入 `backend/migrations/versions/0001_initial.py` 初始结构基线
- [x] T149 [US7] 实现定时任务、任务状态和审计查询 API 到 `backend/src/easy_quant/api/blueprints/admin_scheduling.py` 与 `backend/src/easy_quant/api/blueprints/audit.py`
- [x] T150 [P] [US7] 实现管理员用户与邀请码页面到 `frontend/src/features/admin-users/pages/` 与 `frontend/src/features/admin-users/api.ts`
- [x] T151 [P] [US7] 实现定时任务、后台任务和审计页面到 `frontend/src/features/admin-scheduling/pages/` 与 `frontend/src/features/admin-scheduling/api.ts`
- [x] T152 [US7] 实现前端角色路由守卫和无权限状态到 `frontend/src/app/route-guards.tsx` 与 `frontend/src/components/app-shell/forbidden.tsx`
- [x] T153 [US7] 为策略、回测、实盘、通知和任务 API 接入统一资源归属策略到 `backend/src/easy_quant/application/authorization.py`
- [x] T154 [US7] 添加初始化—邀请—普通用户—管理员任务管理的浏览器验收测试到 `frontend/tests/e2e/admin-and-invitation.spec.ts`

**Checkpoint**: 管理员拥有明确的全局管理能力，普通用户之间的私有资源隔离全部通过。

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: 完成安全、部署、Living Docs、跨故事验收和项目交付质量。

- [x] T155 [P] 为所有 API schema 生成并校验 OpenAPI 文档到 `backend/openapi.yaml` 与 `backend/tests/contract/test_openapi.py`
- [x] T156 [P] 添加请求结构化日志、任务关联 ID、敏感字段脱敏和日志测试到 `backend/src/easy_quant/infrastructure/logging.py` 与 `backend/tests/infrastructure/test_logging.py`
- [x] T157 [P] 添加数据库查询索引、分页上限、输出上限和批量写入优化，并将索引纳入 `backend/migrations/versions/0001_initial.py` 初始结构基线
- [x] T158 执行会话、CSRF、邀请码、密钥加密、策略子进程环境和越权访问安全加固到 `backend/src/easy_quant/` 与 `backend/tests/security/`
- [x] T159 [P] 创建生产后端/前端镜像和单机编排到 `backend/Dockerfile`、`frontend/Dockerfile` 与 `deploy/compose.yaml`
- [x] T160 [P] 添加数据库迁移、API 健康检查、worker 健康状态和备份/恢复脚本到 `tools/migrate.ps1`、`tools/health.ps1` 与 `tools/backup.ps1`
- [x] T161 创建从安装、初始化管理员、配置来源到运行首个回测的验证指南到 `specs/001-platform-foundation/quickstart.md`
- [x] T162 [P] 更新系统当前架构、模块边界和运行拓扑到 `docs/系统架构.md`
- [x] T163 [P] 编写当前数据集、来源、缓存、覆盖和数据时间语义到 `docs/数据平台.md`
- [x] T164 [P] 编写当前因子目录、策略模板、示例策略与执行限制到 `docs/因子与策略.md`
- [x] T165 [P] 编写当前回测口径、实盘建议、实际操作账本和通知语义到 `docs/回测与实盘.md`
- [x] T166 [P] 编写当前部署、配置、调度、备份和故障恢复到 `docs/部署与运维.md`
- [x] T167 更新项目定位、功能、目录、快速开始、免责声明和文档导航到 `README.md`
- [x] T168 编写面向后续开发代理的中文协作、目录边界、测试、文档和安全规则到 `AGENTS.md`
- [x] T169 更新 Git 忽略项、钩子命令和实际质量门禁到 `.gitignore`、`.pre-commit-config.yaml`、`tools/check_commit_message.py` 与 `docs/Git 协作规范.md`
- [x] T170 [P] 添加数据获取—因子—策略—回测的本地 fake API 浏览器验收到 `frontend/tests/e2e/backtest-journey.spec.ts`
- [x] T171 [P] 添加回测—实盘—通知—确认/拒绝/修正的本地 fake API 浏览器验收到 `frontend/tests/e2e/live-journey.spec.ts`
- [x] T172 运行并修复 `uv run ruff format --check .`、`uv run ruff check .`、`uv run pyright`、`uv run pytest`、前端 lint/typecheck/test/build 和 Playwright 离线验收
- [x] T173 对照 59 项 FR、7 项 QR 和 20 项 SC 记录最终可追溯性与验收证据到 `specs/001-platform-foundation/checklists/acceptance.md`
- [x] T174 按实现结果更新所有 `docs/` Living Docs，删除未来时态和未实现描述，并复核其与 `README.md`、宪章、规格和代码一致

**Checkpoint**: 单机部署可启动，全部离线质量门禁与验收场景通过，Living Docs 仅描述真实已实现状态。

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 — Setup**: 无依赖，可立即开始。
- **Phase 2 — Foundational**: 依赖 Phase 1，阻塞所有用户故事。
- **Phase 3 — US1 数据平台**: 依赖 Phase 2；是 US2、US4、US5 的数据前提。
- **Phase 4 — US2 因子**: 依赖 Phase 3 的内部数据契约和数据网关。
- **Phase 5 — US3 策略**: 依赖 Phase 4 的因子注册表和上下文。
- **Phase 6 — US4 回测**: 依赖 US1、US2、US3。
- **Phase 7 — US5 实盘建议**: 依赖 US4 的成功回测、US3 的策略运行和 US1 的数据获取。
- **Phase 8 — US6 实际操作**: 依赖 US5 的实盘实例与建议。
- **Phase 9 — US7 管理平台**: 身份基础依赖 Phase 2；完整页面和跨资源授权依赖前述故事已注册资源。其定时任务实现可在 Phase 3 后提前并行。
- **Phase 10 — Polish**: 依赖计划交付范围内的所有用户故事。

### User Story Dependency Graph

```text
Setup → Foundation → US1 Data → US2 Factors → US3 Strategies → US4 Backtests → US5 Live → US6 Actual Operations
                      └──────────────────────────────────────────────────────────────►
Foundation → US7 Identity/Admin ── integrates with every completed resource ────────► Polish
```

### Within Each User Story

1. 契约和风险测试可与领域实体并行编写。
2. 领域实体与端口完成后实现应用服务。
3. 应用服务完成后接入基础设施仓储、worker 和外部适配器。
4. 后端 API 稳定后实现前端 hooks 和页面；前端可先使用固定 mock 并行开发。
5. 故事结束前运行该故事全部后端、前端和契约测试，并核对独立验收描述。

## Parallel Opportunities

- T002–T003、T006–T009、T011–T012 可在 T004 的目录骨架约定明确后并行。
- T014–T017、T020、T022、T025、T027–T028、T033、T035–T036 可按文件边界并行。
- US1 的数据契约、两种来源适配器、上传模板和前端 mock 页面可并行，最终在 T046/T051/T058 汇合。
- US2 的 K 线/市值、均线和复杂因子可并行实现。
- US3 的两个示例策略、持久化、子进程与前端 mock 页面可并行，统一通过策略契约测试汇合。
- US4 的执行模型、指标、快照和前端结果视图可并行，最终由回测服务集成。
- US5 的邮件与 ntfy 适配器、实盘页面和通知设置页面可并行。
- US7 的用户管理和定时任务管理可分两条工作流并行。
- Phase 10 中标记 `[P]` 的文档、部署、日志、性能和浏览器测试可由不同人员并行，但 T174 必须最后执行。

## Implementation Strategy

### MVP First

1. 完成 Phase 1 与 Phase 2。
2. 完成 US1，交付可在 PC 管理页面配置来源、拉取和上传股票数据的数据平台 MVP。
3. 停止并独立验证 US1，不等待策略与回测模块。

### Incremental Delivery

1. US1：可靠获取与管理数据。
2. US2：以稳定因子接口消费数据。
3. US3：在页面编写并运行策略。
4. US4：形成可复现的策略评价闭环。
5. US5：把成功回测转为持续建议与通知。
6. US6：用实际操作闭合实盘状态。
7. US7：完成管理员和多用户治理。
8. 最后完成安全、部署、Living Docs 和全链路验收。

## Notes

- 任务中的测试不得访问网络、真实 MariaDB、真实 ntfy、SMTP 或其他第三方服务。
- 不以 SQLite 冒充 MariaDB 行为；默认测试使用 in-memory 端口实现和 SQL 编译检查。
- `[P]` 只表示文件和直接依赖允许并行，不代表可以越过阶段门禁。
- 每个任务或紧密相关的小组应形成可说明、可验证的提交，并同步相关测试和 Living Docs。
- `docs/` 只在对应能力真实实现后更新为当前状态；设计中的未来内容保留在 `specs/001-platform-foundation/`。
- 任何新增 Redis、Celery、对象存储、微服务、分布式锁或自动下单能力的提议都超出本任务清单，必须先修订规格与计划。

## Phase 11: Convergence

- [x] T175 CRITICAL 修正 README、Living Docs、验收清单与任务状态中把未接通能力表述为已完成的问题，并只按真实浏览器验收结果恢复完成声明 per Constitution 治理与 Living Docs (contradicts)
- [x] T176 CRITICAL 实现配置驱动的首次管理员自动创建、登录、邀请码注册、全局登录守卫、角色守卫、用户菜单和登出切换用户闭环 per FR-002、FR-003、US7 (contradicts)
- [x] T177 CRITICAL 接通 Vite 开发代理与健壮 API 错误解析，确保前后端联合开发时所有 `/api/v1` 请求到达 Flask 且空响应不会触发 JSON.parse 崩溃 per FR-001、US1/AC1、US4/AC1 (missing)
- [x] T178 CRITICAL 将身份、策略、数据目录、回测、通知和管理状态统一装配进应用容器并移除各蓝图互不共享的模块级假数据，提供可替换持久仓储边界 per FR-004、FR-005、FR-055、plan: storage decision
- [x] T179 CRITICAL 实现可用的数据管理控制台，包括数据集加载、来源启停、拉取任务状态、CSV 预检与确认导入以及可操作错误状态 per FR-006–018、US1
- [x] T180 实现完整策略工作台：加载列表、创建与新版本保存、草稿持久化、可用模板与两个参考示例、运行输出，并让策略 context 可调用平台因子产生选股与交易信号 per FR-027–035、SC-007、SC-008 (partial)
- [x] T181 实现因子目录和详情的数据加载、搜索、参数/输入/输出/时间语义/调用示例展示，并至少完整呈现 5 日均线因子 per FR-019–025、SC-005 (partial)
- [x] T182 重做回测创建与结果闭环：从用户策略选择不可变版本、移除脱离策略的标的输入、统一 shadcn 表单、执行实际日频回测并跳转查看状态与结果 per FR-036–042、US4
- [x] T183 实现系统管理首页与用户、邀请码、定时任务、后台任务和审计子页导航及真实数据装载和操作反馈 per FR-004、FR-055、US7 (missing)
- [x] T184 将通知设置加入用户导航，完成邮件/ntfy 订阅列表、创建、启停及投递状态反馈 per FR-052–054、US5 (partial)
- [x] T185 使用现有 shadcn 组件统一登录、策略、因子、回测、数据管理和系统管理页面的表单、卡片、表格、空状态、加载与错误反馈 per QR-005、QR-007 (partial)
- [x] T186 替换掩盖断链的浏览器 route mock，新增真实 Flask+Vite 联合验收，覆盖管理员自动初始化、登录/登出、邀请注册、策略保存与刷新、因子查看、回测创建、数据管理、系统管理和通知订阅 per SC-007、SC-013、SC-015 (partial)

## Phase 12: Code Quality Tooling

- [x] T187 配置 Prettier、Tailwind class 排序、ESLint import/TypeScript/React 可访问性规则，并对现有前端代码执行全量格式化
- [x] T188 将前端 Prettier/ESLint/TypeScript 与后端 Ruff/Pyright 接入 pre-commit 自动修复和快速扫描
- [x] T189 配置 VS Code 保存时格式化、ESLint 修复和推荐扩展，并同步 README 与 Git 协作规范

## Phase 13: 真实数据、持久回测与三阶段策略闭环

- [x] T190 CRITICAL 修正数据源契约为可注入随机起选、来源内有限重试、失败遍历剩余来源，并保存全部尝试原因；移除管理员优先级语义 per FR-006–008
- [x] T191 CRITICAL 新增沪深京证券基础信息、交易日历与日线覆盖聚合模型、迁移和仓储，提供完全同步/部分同步/数据不足/未同步以及已更新/已过时判定 per FR-060–061、FR-071
- [x] T192 CRITICAL 接通 AKShare 与东方财富真实证券列表、基础信息和日线适配器到原始缓存、归一化仓储和获取任务；所有来源失败才报告 per FR-009–015、FR-057–059
- [x] T193 实现管理员单票/多票日期范围同步、全量/单票基础信息刷新、每日上一交易日日线任务及来源诊断 API per FR-062–063
- [x] T194 实现数据总览、证券覆盖表、筛选与批量同步、基础信息刷新、每日任务配置，以及已过时股票补齐到上一交易日/盘后今日的操作前端；所有文案中文且数值不溢出 per FR-060–063、FR-068、FR-071
- [x] T195 CRITICAL 实现策略数据依赖声明、覆盖校验和结构化缺失数据错误，彻底移除回测合成/Mock 行情回退并给出同步入口 per FR-066
- [x] T196 CRITICAL 实现回测快照、运行、输出、周期、交易和指标仓储及事务装配，新增用户回测记录列表并验证进程重启后可恢复 per FR-039、FR-067
- [x] T197 将回测状态、指标、交易动作和假设映射为中文，统一 Decimal API/前端格式化与防溢出展示 per FR-041、FR-067–068
- [x] T198 CRITICAL 扩展策略模板、校验器和受限运行器，支持盘前、盘中、盘后三个钩子及阶段化真实数据 context per FR-064
- [x] T199 CRITICAL 在回测事件循环中按交易日执行三阶段钩子并注入禁用通知端口，验证时间一致性和零通知 per FR-037、FR-064、FR-069
- [x] T200 CRITICAL 实现实盘盘前信号通知、盘中固定频率盯盘与触价/仓位判断、当日有建议时盘后仓位提醒，并保证建议与通知幂等 per FR-044–050、FR-069
- [x] T201 建立内部大数策略能力映射和离线验收 fixture，验证经适配拆分后可完成选股、回测和实盘建议；确保其不出现在示例策略目录/API/UI per FR-065、FR-070
- [x] T202 添加数据缺失阻断、来源随机故障转移、覆盖状态、持久回测、中文精度展示、三阶段生命周期和实盘通知的后端/前端/E2E 测试 per QR-001–008
- [x] T203 同步 README、OpenAPI、quickstart 与 Living Docs，只描述已真实接通的能力并删除合成行情限制说明

## Phase 14: 全环境持久化与首次发布基线

- [x] T204 移除按环境选择进程内仓储的运行时分支，使 API 与 worker 始终从 `EASY_QUANT_DATABASE_URL` 装配 SQLAlchemy 仓储
- [x] T205 将数据库 URL 改为必填配置并删除 `EASY_QUANT_ENVIRONMENT`，补充默认装配回归测试
- [x] T206 将 Playwright 与 API 测试的 fake 容器改为测试代码显式注入，确保其不构成应用运行模式
- [x] T207 将尚未发布的数据库演进脚本整理为单一 `0001_initial` 全新结构基线，并移除旧策略入口兼容
- [x] T208 同步宪章、规格、计划、验收证据、README 与 Living Docs，明确所有运行环境持久化和当前无历史数据迁移

## Phase 15: 后台任务接线、策略快测与证券分页详情

- [x] T209 CRITICAL 将数据同步、策略单日快速测试和回测 API 改为持久 job 入队并快速响应，注册真实 worker handlers，修复任务状态与关联业务记录的成功/失败迁移 per FR-074–076、SC-021
- [x] T210 实现策略指定交易日完整 Tick 的时间一致上下文、阶段化信号/标准输出结果及最近运行轮询页面 per FR-033、FR-064、FR-074
- [x] T211 实现回测排队记录、worker 原位执行与失败持久化，前端创建后跳转并轮询状态 per FR-039、FR-067、FR-075–076
- [x] T212 实现证券覆盖服务端分页、代码/名称搜索和同步状态筛选，并更新数据管理页面 per FR-060、FR-077、SC-022
- [x] T213 实现证券详情与按日期范围查询日线 API、路由和 K 线图页面 per FR-078、SC-023
- [x] T214 添加 API、worker、前端与离线 E2E 回归测试，并同步 OpenAPI、README 和 Living Docs

# 数据模型：Easy Quant 易量化平台基础能力

本文定义首期持久化模型、聚合边界、状态机和关键索引。数据库时间统一使用 UTC；交易日使用市场本地 `date`。金额、价格和费用使用定点小数。

## 身份与访问

### User

- `id`: UUID，主键
- `username`: 唯一、大小写归一化
- `password_hash`: Argon2id
- `role`: `admin | user`
- `status`: `active | disabled`
- `created_at`, `updated_at`

### Invitation

- `id`: UUID，主键
- `token_hash`: 唯一，只保存摘要
- `issued_by_user_id`: 管理员
- `expires_at`, `used_at`, `used_by_user_id`
- 状态由时间及使用字段推导：`active | expired | used | revoked`

### Session

- `id`: UUID，主键；Cookie 仅保存签名后的会话标识
- `user_id`, `csrf_token_hash`, `expires_at`, `revoked_at`
- 索引：`user_id, expires_at`

## 数据目录、来源与缓存

### DatasetDefinition

- `id`, `key`（唯一）、`name`, `schema_name`, `business_key_fields`
- `time_semantics`, `enabled`
- 首期数据集：证券列表、日线 K 线、公司资料、主要股东、概念板块、市值

### DataSource

- `id`, `key`（唯一）、`provider`, `access_method`
- `supported_datasets`, `credentials_encrypted`, `enabled`
- `freshness_seconds`, `retention_seconds`, `max_attempts`, `backoff_policy`, `rate_limit`

### SourceBinding

- `id`, `dataset_id`, `source_id`, `enabled`
- 唯一键：`dataset_id, source_id`
- 同一数据集的已启用来源不设优先级；每次采集随机选择起始来源，失败后继续尝试其余来源。

### AcquisitionRun / SourceAttempt

- `AcquisitionRun`: `id`, `dataset_id`, `semantic_request_hash`, `requested_range`, `actual_range`, `status`, `final_source_id`, `record_count`, `warning_count`, `started_at`, `finished_at`
- `SourceAttempt`: `id`, `run_id`, `source_id`, `attempt_number`, `status`, `page_count`, `declared_count`, `actual_count`, `error_code`, `error_summary`
- 运行状态：`queued → running → succeeded | partial | failed | cancelled`

### RawResponseCache

- `id`, `source_id`, `dataset_id`, `semantic_request_hash`, `page_identity`
- `content_type`, `encoding`, `response_metadata`, `payload_compressed`, `payload_sha256`
- `fetched_at`, `fresh_until`, `retain_until`
- 唯一键：`source_id, dataset_id, semantic_request_hash, page_identity, fetched_at`
- 本实体不通过产品 API 暴露。

### 规范化数据

- `Instrument`: 市场内稳定身份、当前代码、名称、币种、交易日历、有效期
- `DailyBar`: `instrument_id, trade_date, adjustment` 为业务键；OHLCV、币种、时区、来源、`available_at`
- `CompanyProfile`: `instrument_id, effective_date` 为业务键；公司与上市资料
- `ShareholderSnapshot`: `instrument_id, report_date, holder_identity` 为业务键；公告日作为 `available_at`
- `ConceptBoard`: `board_code, effective_date` 为业务键
- `InstrumentConcept`: `instrument_id, board_id, effective_from` 为业务键
- `MarketCapitalization`: `instrument_id, trade_date` 为业务键；总市值、流通市值、`available_at`
- 重复业务键执行当前值 upsert，并追加审计事件。

## 因子与模型

因子不建数据库实体。代码注册表提供名称、说明、参数、输入、输出、时间语义和示例。随发布模型通过只读 `manifest.json` 描述因子名、权重路径、SHA-256 和应用兼容信息。

## 策略

### StrategyDefinition

- `id`, `owner_user_id`, `name`, `description`, `status`, `is_example`
- 普通用户只能访问自己的定义；示例策略全局只读并允许复制。

### StrategyVersion

- `id`, `strategy_id`, `version_number`, `parent_version_id`
- `source_code`, `parameter_schema`, `factor_dependencies`, `content_sha256`
- `created_by_user_id`, `created_at`
- 唯一键：`strategy_id, version_number`；保存后不可修改。

### StrategyRun

- `id`, `strategy_version_id`, `owner_user_id`, `job_id`, `status`
- `input`, `result`, `stdout`, `stderr`, `warnings`, `failure_code`
- `started_at`, `finished_at`

## 回测

### DataSnapshot / DataSnapshotChunk

- `DataSnapshot`: `id`, `dataset_query`, `application_release`, `content_sha256`, `record_count`, `created_at`
- `DataSnapshotChunk`: `snapshot_id, sequence`, `payload_compressed`, `payload_sha256`
- 内容哈希唯一；创建后不可修改。

### BacktestRun

- `id`, `owner_user_id`, `strategy_version_id`, `snapshot_id`, `job_id`
- `configuration`, `random_seed`, `status`, `progress`, `failure_code`
- `started_at`, `finished_at`

### BacktestPeriod / SimulatedTrade / BacktestMetric

- 周期记录保存交易日、现金、权益和持仓摘要。
- 模拟交易保存信号、方向、数量、价格、费用、滑点和未成交原因。
- 指标以 `(backtest_id, metric_key)` 唯一并记录口径。

## 实盘建议与账本

### LiveInstance

- `id`, `owner_user_id`, `strategy_version_id`, `source_backtest_id`
- `parameters`, `initial_cash`, `initial_positions`, `status`, `next_decision_at`
- 状态：`active ↔ paused → terminated`；终止不可恢复。

### Recommendation

- `id`, `live_instance_id`, `strategy_version_id`, `decision_at`, `instrument_id`
- `signal_key`, `action`, `quantity_or_target`, `reason`, `status`, `lock_version`
- 唯一键：`live_instance_id, strategy_version_id, decision_at, instrument_id, signal_key`
- 状态：`pending → confirmed | rejected | corrected`。

### ActualOperation / PortfolioLedgerEntry

- `ActualOperation`: `id`, `recommendation_id`, `live_instance_id`, `actor_user_id`, `direction`, `quantity`, `price`, `fee`, `executed_at`, `idempotency_key`
- `PortfolioLedgerEntry`: `id`, `live_instance_id`, `operation_id`, `entry_type`, `cash_delta`, `instrument_id`, `quantity_delta`, `cost_delta`, `occurred_at`
- 实际操作幂等键唯一；账本只追加，当前组合必须可从初始状态重建。

## 通知

### NotificationSubscription

- `id`, `owner_user_id`, `channel_type`, `configuration_encrypted`, `enabled`

### NotificationDelivery

- `id`, `recommendation_id`, `subscription_id`, `channel_type`, `status`
- `attempt_count`, `next_attempt_at`, `last_error`, `sent_at`
- 唯一键：`recommendation_id, subscription_id, channel_type`
- 状态：`pending → sending → sent | retryable_failed | abandoned`

## 调度、任务与审计

### ScheduledTask

- `id`, `task_type`, `schedule_kind`, `schedule_expression`, `timezone`, `configuration`, `enabled`, `next_run_at`

### Job

- `id`, `job_type`, `business_key`（唯一）、`payload`, `status`, `attempt_count`
- `available_at`, `lease_owner`, `lease_until`, `result_summary`, `error_summary`
- 状态：`queued → running → succeeded | failed | cancelled`；租约过期的 `running` 可重新领取。

### AuditEvent

- `id`, `actor_user_id`, `trigger_source`, `action`, `resource_type`, `resource_id`
- `before_summary`, `after_summary`, `correlation_id`, `occurred_at`
- 只追加；按资源、操作者、关联 ID 和时间建立索引。

## 删除和保留

- 用户可管理资源优先使用停用状态。
- 策略版本、运行、快照、回测、建议、实际操作、账本和审计不可物理删除。
- 原始响应按来源与数据集的保留策略清理；清理不得影响已经物化的回测快照。

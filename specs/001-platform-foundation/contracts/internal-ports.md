# 内部端口契约

## 通用原则

- 端口定义在 `application/ports`，领域与应用层不得导入具体基础设施。
- 所有时间来自 `Clock`，等待来自 `Sleeper`，标识来自 `IdGenerator`。
- 写用例在 `UnitOfWork` 内提交；失败必须回滚。
- 外部错误转换为稳定错误代码，原始异常只能进入脱敏日志。

## SourceAdapter

```python
class SourceAdapter(Protocol):
    key: str

    def capabilities(self) -> tuple[str, ...]: ...
    def semantic_request(
        self, dataset: str, request: Mapping[str, object]
    ) -> SemanticRequest: ...
    def fetch_raw(self, request: SemanticRequest) -> RawEnvelope: ...
    def parse(self, raw: RawEnvelope) -> ParsedDataset: ...
```

- `fetch_raw` 不执行领域字段映射。
- `RawEnvelope` 对 HTTP 保存正文 bytes；对 AKShare 保存其返回表格的稳定、带 schema 表示。
- `parse` 必须确定性执行，可在无网络环境从缓存重新运行。
- 适配器声明重试分类、最大次数、退避、频率限制、新鲜期和保留期。

## RawCache

```python
class RawCache(Protocol):
    def find_fresh(
        self, source: str, request_hash: str, at: datetime
    ) -> RawEnvelope | None: ...
    def put(
        self, source: str, request_hash: str, raw: RawEnvelope
    ) -> CacheIdentity: ...
    def get(self, cache_id: CacheIdentity) -> RawEnvelope: ...
```

- 缓存命中范围限定为相同来源与语义请求。
- payload 使用 SHA-256 校验；损坏缓存等同未命中并产生诊断。
- 端口不向 Web API 暴露枚举或下载能力。

## FactorRegistry / FactorContext

```python
class Factor(Protocol):
    descriptor: FactorDescriptor

    def calculate(self, context: FactorContext, **parameters: object) -> object: ...


class FactorContext(Protocol):
    as_of: datetime

    def query(self, dataset: str, query: Mapping[str, object]) -> Sequence[object]: ...
    def factor(self, name: str, **parameters: object) -> object: ...
```

- 数据网关强制 `available_at <= as_of`。
- 注册表随应用发布，只读，不提供用户增删改。
- 同一应用发布、输入、`as_of` 和随机种子必须得到相同结果。

## StrategyRunner

```python
class StrategyRunner(Protocol):
    def validate(self, source: str) -> ValidationResult: ...
    def run(self, request: StrategyRunRequest) -> StrategyRunResult: ...
```

- 请求只含策略源码、参数、受控因子调用上下文和限制。
- 结果分离返回值、标准输出、标准错误、警告和失败代码。
- 实现必须有墙钟超时、输出上限、临时目录和密钥环境清理。
- 该端口用于可信代码的故障隔离，不承诺恶意代码安全沙箱。

## NotificationChannel

```python
class NotificationChannel(Protocol):
    channel_type: str

    def send(self, message: NotificationMessage) -> DeliveryResult: ...
```

- `DeliveryResult` 明确 `sent | retryable_failure | permanent_failure`。
- 渠道不修改建议状态。
- 投递幂等由应用层的建议、订阅和渠道组合键保证。

## JobRepository

```python
class JobRepository(Protocol):
    def enqueue(self, job: Job) -> Job: ...
    def claim_due(
        self, worker_id: str, now: datetime, lease_until: datetime
    ) -> Job | None: ...
    def renew(self, job_id: str, worker_id: str, lease_until: datetime) -> None: ...
    def succeed(self, job_id: str, summary: Mapping[str, object]) -> None: ...
    def fail(self, job_id: str, error: JobError, retry_at: datetime | None) -> None: ...
```

- `business_key` 唯一；重复入队返回已有逻辑任务。
- 只有租约持有者可完成或失败任务。
- 租约过期的运行任务允许重新领取，业务副作用仍须幂等。

## Repository / UnitOfWork

- 仓储按聚合提供 `get`、受约束的查询、`add` 和明确状态更新，不向应用层暴露 ORM query。
- `UnitOfWork` 提供所需仓储、`commit()` 和 `rollback()`。
- 自动化测试使用行为等价的 in-memory 实现，不连接 MariaDB 或 SQLite。

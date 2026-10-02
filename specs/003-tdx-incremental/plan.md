# 实现计划

先分析固定参考提交 `80b287bf65019c79ff8db40ee42db5389f874731` 的 `workflow/task_daily.go`、`workflow/tdx_helper.go`、`tdx/merge.go`、`tdx/holidays.go`。Python 适配器直接读取 ZIP 中的 COD 150 字节记录及 MD1 512 字节块，不解压、不执行 datatool、不重建本地全量 DAY。

应用服务通过 feed/store 端口和注入时间实现有界日期编排。新增 MariaDB 按日期检查点表，状态为 succeeded/closed/pending/failed；成功状态及当日全市场写入同事务。独立表避免污染全量股票检查点。SQL upsert 复用现有字段归一化和同口径保护。摘要变化允许纠正同日行情；日期并发写入通过单机数据库互斥边界串行化。

下载保留在被忽略的 backend/.local-data/tdx/daily，大小限制与 ZIP CRC 校验在适配器完成，HTTP/数据库异常脱敏。日历使用同一官方公共归档，严格校验嵌套 ZIP 和年度声明；下载失败使本次任务失败，防止错误认定休市。每次任务检查最近七个自然日并恢复更早的 pending/failed。CLI 支持明确日期，worker 使用现有 cron 任务和结果记录，页面新增任务类型。

## 宪章检查

- 日频、决策辅助；不扩展自动交易、高频、公共注册或分布式架构。
- 领域无 I/O；时间注入，外部网络/SQL/ZIP 位于适配器。
- 延续不复权元/股口径及来源摘要，不混入公开接口前复权数据。
- 运行使用现有 MariaDB；测试使用内存 ZIP、fake 仓储、httpx MockTransport 和 SQL 编译，不访问真实存储。
- 日期级事务、缺口恢复和业务主键保障幂等；异常脱敏，不提交凭据或行情归档。
- 设计先于实现；测试、Living Docs、质量门禁和真实人工验证与代码同步。

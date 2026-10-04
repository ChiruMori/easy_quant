# 任务

## 基础与查询

- [x] [T001] 在 `backend/migrations/versions/` 与 `backend/src/easy_quant/infrastructure/persistence/models/market_data_records.py` 增加覆盖型运行索引，治理旧日期索引；在 `backend/tests/infrastructure/` 验证 SQL 投影、索引和迁移可逆性。此原方案已由 T010 撤销，保留任务记录以说明设计纠偏。
- [x] [T002] 在 `backend/src/easy_quant/infrastructure/persistence/repositories/runtime.py` 增加只读 OHLC/可获知时间投影及按日页读取；实现单任务 12 页 LRU，补充离线命中、缺页、淘汰和无跨任务陈旧缓存测试。
- [x] [T003] 在 `backend/src/easy_quant/application/services/strategy_quick_test.py` 接入按日页缓存与分阶段计时，保持 5 日和三阶段隔离；补 API/worker 回归。

## 实盘与回测

- [x] [T004] 在 `backend/src/easy_quant/application/services/strategy_validation.py` 增加 `HISTORY_TRADING_DAYS` 静态声明及范围校验；在实盘路径按交易日窗口读取，不再查询全史，补长回溯及未来数据测试。
- [x] [T005] 重构 `backend/src/easy_quant/application/services/backtest_runtime.py` 与领域引擎，按日分组/滚动历史线性推进；用离线多年合成数据验证结果等价与增长趋势。
- [x] [T006] 在 `backend/src/easy_quant/infrastructure/strategy_runtime/` 加受限子进程流式日 Tick 协议，避免多年回测重复启动与发送全量历史；补超时、崩溃和隔离测试。
- [x] [T007] 在回测路径按日页流式读取，在持久层流式构造快照并分块压缩保存，保持快照哈希和原有审计契约，补复现与内存边界测试。

## 验收和文档

- [x] [T008] 更新 `docs/` 的当前行为、缓存选择、MariaDB 缓冲池建议、18M 表迁移及回退操作；在 UI 说明实盘/回测默认回溯窗口。
- [x] [T009] 运行 Ruff format/check、`pnpm check`、受影响 Playwright、pre-commit；对本地 MariaDB 做只读执行计划/计时，记录未部署索引与已部署索引的差异。若仍与目标差距较大，暂停分表工作并报告设计依据。开发库未执行大表 DDL，因此仅有旧索引基线；迁移后新索引的真实耗时与 `EXPLAIN` 留待维护窗口验收。

## 中断迁移后的设计纠偏

- [x] [T010] 修订 `0008` 与模型，停止创建宽索引；对版本仍为 `0007` 且已存在宽索引的状态提供幂等清理路径，保留日期与覆盖统计索引，补迁移测试。
- [x] [T011] 将运行行情查询改为日期索引找标的、主键批量范围读取；按月流式回测及按日期重排，按窗口批量预取 LRU 日页；补离线 SQL 形态、时间可见性与缓存测试。
- [x] [T012] 更新 `docs/` 的真实索引状态、维护流程和性能限制；执行格式、类型、后端及浏览器测试，并仅用只读 SQL 复核现有 MariaDB，不运行 DDL。

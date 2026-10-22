# 实施计划

复用行情仓储、回测仓储和实盘账本快照。新增受认证的只读比较接口，仅查询已有行情；服务校验对象归属、可比配置、日期及 Decimal 归一，指数与股票保留独立代码空间。回测/实盘页面只映射主曲线与默认基准，共用组合图表、单位切换和临时比较管理，避免复制绘图与搜索逻辑。

沿用 IconButton、ConfirmAction、Popover、Tooltip、Select、ToggleGroup。扩展操作分页端口的 status/operation_type，搜索只匹配标的/日期/说明。通知复用现有持久 delivery、outbox 和 worker 重试任务，补发送前记录与失败更新、每阶段聚合和无渠道诊断；不加表、外键、中间件或自动交易。外部发送不占用实盘锁，应用日志和 UI 诊断均脱敏。

宪章检查：仅日线辅助分析；策略版本和原回测结果不变；金额 Decimal、显式时区和注入时钟；测试使用内存仓储、fake 渠道和本地 Playwright；同步 docs、OpenAPI。执行 Ruff、前端 format/lint:fix、pnpm check、相关 Playwright、pre-commit，再提交推送并更新当前 PR。

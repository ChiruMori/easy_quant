# 验证记录

- 2026-11-17复核 [Tushare公开公式](https://tushare.pro/document/2?doc_id=486) 及 [TA-Lib Python官方说明](https://github.com/TA-Lib/ta-lib-python)。财报字段与现有规范化映射逐项核对，本轮不访问真实存储、不执行采集或回填。
- 当前公开202项支持105项、未注册97项，新增20个财务计算；未公开70个Alpha101仍不声明支持。未删除原85项，修正Alpha101退化单标的截面和Size对输入排序的隐式依赖。
- TA-Lib 0.6.8已通过uv安装到backend/.venv，锁文件包含部署平台wheel；保留现有Docker uv sync流程，无需增加系统编译步骤。本机运行Python3.13.5，未执行容器镜像构建。
- 子进程测试实际调用TA-Lib SMA、RSI，验证普通与流式协议财务/指标输出一致；非法导入、内部属性、数组文件接口和全局配置受限。普通策略不加载TA-Lib/NumPy，保留一秒超时回收测试，未调大超时掩盖启动开销。
- 财务回归覆盖TTM/单季/年度手算、同比报告季度、未来修订、旧报告新修订、缺期、币种/范围/来源、非正分母、截面并列与缺失成员、未来市值及未来报告期；相关50项测试通过。
- Playwright：strategy-workspace与backtest-journey两个旅程通过（含360px布局）。既有E2E测试容器的预期失败路径产生未同步行情/通知handler日志，不影响两项断言通过。
- 最终`pnpm check`通过：938项后端测试、67项前端测试、Ruff/Pyright、前端格式/ESLint/TypeScript及生产构建。`pre-commit run --all-files`通过。构建保留既有大chunk提示，本轮无前端代码变更。
- 交付分支`feat/financial-factors-talib`，实现提交`d4ba5bd`，[PR #31](https://github.com/ChiruMori/easy_quant/pull/31)以master为目标。GitHub连接器创建PR返回403，随后使用已有本机Git认证创建成功。

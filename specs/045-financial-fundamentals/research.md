# 原始接口调研（2026-11-01）

依据 AKShare 官方 `docs/data/stock/stock_finance.md` 与已安装适配器源码追溯原站。12个组合的只读探测成功，不写数据库；测试不重复真实网络探测。

- 东财三表：NewFinanceAnalysis/Index 的 hidctype 识别公司类型（000001银行=3），zcfzb/lrb/xjllbDateAjaxNew 获取完整报告期，按5日期批次调用对应 AjaxNew，reportType=1合并、reportDateType=0。
- 东财指标：datacenter securities/api/data/get，type=RPT_F10_FINANCE_MAINFINADATA，sty=APP_F10_MAINFINADATA，按 SECUCODE 过滤，p/ps=100分页。ROEJQ为百分数。
- 东财概况、分红、股东：data/v1/get，分别 RPT_F10_ORG_BASICINFO、RPT_SHAREBONUS_DET、RPT_HOLDERNUM_DET；检查 success、result、count、pages，按100分页。概况原响应有联系方式，适配器投影后才缓存；注册资本单位万元。
- 主营：BusinessAnalysis/PageAjax 的 zygcfx，分类+项目+报告期保留；MBI/MBC/MBR_RATIO与毛利率是小数，转百分数。无可核实版本时间时从采集可见。
- 新浪：CompanyFinanceService.getFinanceReport2022，source=fzb/lrb/llb/gjzb，paperCode带市场前缀，type=0合并，num=100分页。report_list以YYYYMMDD为键；科目 item_field/title/value，重复字段取首项。publish_date为日期，update_time为秒时间戳；指标可能缺update_time。

探测000001三表与指标分别为百余历史报告，单源单股票通常数十至数百KB响应。保留季度版本而非按交易日复制，数量远小于日线；复用原基本面表，未申请新表或日线改动。研究未保存含联系方式的原始概况。无历史修订证明时按实际观测边界处理，不声称拥有完整历史PIT数据库。

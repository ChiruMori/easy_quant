# 任务

- [x] T001 低频只读探测与接口口径核验
- [x] T002 主营报告期批量采集、字段投影与升级续传
- [x] T003 离线回归与当前文档
- [x] T004 执行全量检查并独立复查失败项（未全部通过，见验证记录）
- [x] T005 提交推送：1f29185，沿用 fix/fundamental-collection-reports
- [ ] T006 创建PR：本轮再次返回403 Resource not accessible by integration，标题与描述保存在 ../049-fundamental-collection-reports/pr.md。

定向离线测试35条通过。全量执行与独立复查结果见 [validation.md](validation.md)，后端启动超时最终精确复查通过，浏览器仍有2条既有等待超时，未放宽断言或时限。

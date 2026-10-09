# 任务

- [x] T001 查证上游原因并复现 pwritev2 EPERM。
- [x] T002 替换 Debian 运行镜像及健康命令，添加 CI 兼容启动回归。
- [x] T003 同步运维文档并运行门禁及镜像验收。
- [ ] T004 提交推送 master 并验证镜像发布结果。

本地验收（2026-10-09）：旧 Alpine 镜像在单独拒绝 pwritev2 的 fixture 及移除 pwritev2 许可的 Docker 默认策略下复现同一 PID EPERM。新版镜像实际构建成功，默认启动入口在默认策略、单调用故障模拟策略、移除 pwritev2 许可的默认策略下均正常，健康检查、Nginx 配置及 SPA 路由通过。前端 format/lint:fix、pnpm check（292 后端测试、18 前端单测、构建）、全部 5 项 Playwright、pre-commit --all-files、actionlint 及 Compose 校验通过。没有连接真实数据库/第三方应用服务，未改生产 seccomp；真实 3.10 内核仍需服务器侧验收。

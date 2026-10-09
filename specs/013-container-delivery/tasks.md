# 任务

- [x] T001 交付规格与宪章检查。
- [x] T002 镜像资源、构建上下文排除、三服务外部依赖 Compose。
- [x] T003 master 检查、镜像发布及部署包 workflow。
- [x] T004 同步部署文档与 README。
- [x] T005 验证 Compose、workflow、镜像与项目门禁，记录实测边界。

验收（2026-10-09）：前端 format/lint:fix、pnpm check（292 后端测试、18 前端单测、静态检查及生产构建）、5 项 Playwright 全部通过。Compose 校验仅有三服务，缺少 DATABASE_URL 时失败；actionlint 1.7.12 通过。两个 linux/amd64 镜像实际构建成功；无网络容器验证非 root、模板及公共库、受限策略子进程、迁移 head、Nginx 健康响应及 SPA 路由。冒烟发现并修复 uv 构建缓存的 root 权限问题，运行缓存改为独立临时目录；对应冒烟纳入发布门禁。

未连接真实 MariaDB 或通知服务，未提交/推送及调用 GHCR 发布；迁移与真实环境三服务启动需要部署端验证。工作流端到端及 Packages 权限在首次 master 推送后验证。前端仍有既有的大分块提示。滚动 master 标签更新不原子，部署包固定相同完整 SHA。

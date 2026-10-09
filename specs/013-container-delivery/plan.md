# 实施计划

宪章检查：仅改变单机交付，维持 MariaDB 持久化、单 worker、受限策略子进程、受控邀请与人工交易；不新增队列或第三方组件。凭据只留部署端，验证不连接真实数据库或第三方应用服务。

1. 后端在 /app/backend 安装冻结生产依赖，虚拟环境位于 backend/.venv，命令使用 uv run --project backend，复制迁移、模板及 src 资源。
2. 前端 pnpm 构建、Nginx 同源代理；分别维护构建上下文白名单。
3. Compose 拉取 GHCR 镜像，只暴露 Web；一次性 api 容器执行迁移，长期进程不竞争迁移。
4. workflow 运行 pnpm check 和 Playwright，顺序发布 linux/amd64 两个 SHA 镜像，镜像离线冒烟成功后更新 master，并上传固定 SHA 部署包。
5. 验证 Compose、workflow、实际镜像构建及离线冒烟。真实数据库迁移和 GHCR 发布待部署环境及推送后验证。

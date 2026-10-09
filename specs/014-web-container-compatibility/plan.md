# 实施计划

宪章检查：只修复镜像交付，不修改领域行为、外部依赖、动态策略隔离或单 worker 架构。测试容器禁止外网，不连接数据库、通知或真实存储。

1. 使用 nginx:1.30.5-trixie（Debian/glibc），以官方已有 curl 替代 Alpine wget 健康检查，固定发行版与版本。
2. 保留原有镜像冒烟，新增真实默认入口的启动验收；分别使用默认 Docker 策略与专用 pwritev2 EPERM 故障模拟策略，检查健康及 SPA 路由。
3. tools/fixtures 下的最小 seccomp 策略仅模拟单个系统调用失败：其他调用允许，不用于生产；测试不注入业务凭据、挂载业务数据或暴露端口，容器运行于 network none 并在结束后清理。
4. 同步部署说明；运行前端格式/lint、项目门禁、Playwright、镜像构建及兼容回归，然后提交推送 master 触发新镜像。

证据：Nginx 上游 issue https://github.com/nginx/docker-nginx/issues/1059；官方镜像变体清单 https://github.com/docker-library/official-images/blob/master/library/nginx。

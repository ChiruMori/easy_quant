# Web 容器旧宿主机兼容修复

问题：Alpine Nginx 1.30.5 在宿主机拦截 pwritev2 时，写 /run/nginx.pid 返回 EPERM，无法启动。用户日志为 CentOS 7 系列 3.10 内核；本地用禁止 pwritev2 的 seccomp 策略已复现相同错误。

要求：Web 运行镜像改用同版官方 Debian 变体，保留三服务编排、API 同源代理、SPA 路由和健康检查；不得通过关闭生产 seccomp 或 privileged 解决。CI 验证默认入口启动及拒绝 pwritev2 时的 HTTP 响应。

验收：旧镜像可复现错误，新镜像在默认策略及故障模拟策略下均正常启动，/healthz 和 /strategies 返回成功。真实 3.10 内核的其余兼容性仍需部署端验收，不声称本地模拟覆盖全部旧系统行为。

# syntax=docker/dockerfile:1.7
FROM node:22-alpine AS build
RUN corepack enable
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

# Debian/glibc 避免新版 musl 的 pwritev2 与旧宿主机 seccomp 不兼容。
FROM nginx:1.30.5-trixie
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD curl --fail --silent --show-error http://127.0.0.1/healthz || exit 1

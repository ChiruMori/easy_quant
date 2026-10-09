# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS runtime

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 UV_CACHE_DIR=/tmp/uv-cache
WORKDIR /app
COPY pyproject.toml uv.lock ./backend/
RUN uv sync --project backend --frozen --no-dev --no-install-project
COPY alembic.ini ./backend/
COPY migrations ./backend/migrations
COPY resources ./backend/resources
COPY src ./backend/src
RUN uv sync --project backend --frozen --no-dev
ENV UV_CACHE_DIR=/tmp/easy-quant-uv-cache
USER 65532:65532
EXPOSE 5000
CMD ["uv", "run", "--project", "backend", "--no-sync", "gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "easy_quant.api.app:create_app()"]

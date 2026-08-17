# syntax=docker/dockerfile:1
#
# AgentFactory Studio — self-host container (Phase 6.2).
#
# One image serves both the platform API and the built Studio SPA. The worker
# (run execution) runs in-process inside the API, so a single container is a
# complete self-host deployment. Production note: run it behind a reverse
# proxy with TLS (see docs/self-host.md) and set a strong
# AGENTFACTORY_JWT_SECRET + AGENTFACTORY_DB_PATH on a persistent volume.

# --- Stage 1: build the Studio SPA -----------------------------------------
FROM oven/bun:1 AS web-build
WORKDIR /app/web
COPY web/package.json web/bun.lock ./
RUN bun install --frozen-lockfile
COPY web/ ./
RUN bun run build

# --- Stage 2: runtime --------------------------------------------------------
FROM python:3.12-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    AGENTFACTORY_SPA_DIR=/app/studio \
    AGENTFACTORY_DB_PATH=/data/agentfactory.db \
    AGENTFACTORY_WORKSPACE_ROOT=/data/workspaces

# Core package + platform extra (uvicorn[standard]: websockets/uvloop).
COPY pyproject.toml README.md ./
COPY agentfactory/ ./agentfactory/
RUN pip install .[platform]

# The built SPA from stage 1.
COPY --from=web-build /app/web/dist /app/studio

# Persistent data (SQLite DB + agent workspace sandboxes).
RUN mkdir -p /data && chmod 755 /data
VOLUME ["/data"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1

# API + SPA in one process; 0.0.0.0 so the container is reachable behind a proxy.
CMD ["uvicorn", "agentfactory.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

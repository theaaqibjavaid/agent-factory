# Self-Hosting AgentFactory Studio

AgentFactory ships as a Python SDK plus the Studio platform (multi-user API +
dashboard UI + terminal + observability). A single process serves everything:
the API, the built SPA, and the run worker (run execution runs in-process), so
self-hosting is one container or one `uvicorn` process.

## Option 1 — Docker (recommended)

The repository's `Dockerfile` builds the Studio SPA (stage 1) and packages the
platform API + SPA into one image (stage 2).

```bash
# Build and run
docker build -t agentfactory .
docker run -d \
  --name agentfactory \
  -p 8000:8000 \
  -e AGENTFACTORY_JWT_SECRET="$(openssl rand -hex 32)" \
  -e AGENTFACTORY_ALLOWED_ORIGINS="https://your.domain" \
  -v agentfactory-data:/data \
  agentfactory
```

Open `http://localhost:8000` and sign up — the first account owns the default
workspace.

> **Important**: replace the JWT secret with your own random value. The
> default only exists for local development. Anyone who knows the secret can
> mint tokens for any user.

### docker-compose example

```yaml
services:
  agentfactory:
    build: .
    ports:
      - "8000:8000"
    environment:
      AGENTFACTORY_JWT_SECRET: "${AGENTFACTORY_JWT_SECRET:?set in .env}"
      AGENTFACTORY_ALLOWED_ORIGINS: "https://your.domain"
    volumes:
      - agentfactory-data:/data
    restart: unless-stopped

volumes:
  agentfactory-data:
```

## Option 2 — Bare metal

```bash
# 1. Install the package with the platform extra (uvicorn[standard]: websockets/uvloop)
pip install 'agentfactory-studio[platform]'

# 2. Build the Studio SPA once
cd web
bun install
bun run build
cd ..

# 3. Run the API + SPA + worker in one process
export AGENTFACTORY_JWT_SECRET="$(openssl rand -hex 32)"
export AGENTFACTORY_SPA_DIR="$(pwd)/web/dist"
export AGENTFACTORY_DB_PATH="/var/lib/agentfactory/agentfactory.db"
export AGENTFACTORY_WORKSPACE_ROOT="/var/lib/agentfactory/workspaces"
uvicorn agentfactory.app.main:app --host 0.0.0.0 --port 8000
```

`AGENTFACTORY_SPA_DIR` makes the API serve the built UI too — no separate
static server needed. Without it, the API is API-only (404 for non-API paths).

## Environment variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `AGENTFACTORY_JWT_SECRET` | Signing secret for auth tokens — **must be set in production** | dev-only fallback |
| `AGENTFACTORY_DB_PATH` | SQLite database path (platform schema + runs) | `agentfactory.db` in CWD |
| `AGENTFACTORY_WORKSPACE_ROOT` | Root that agent sandboxes + terminal sessions are pinned to | CWD `workspaces` |
| `AGENTFACTORY_SPA_DIR` | Directory of the built Studio SPA (served by the API) | empty (API-only) |
| `AGENTFACTORY_ALLOWED_ORIGINS` | Comma-separated CORS origins | `*` (local mode) |
| `MEMORY_DB_PATH` | SQLite path for agent memory stores | `memory.db` |
| `DEV_NOTIF_WEBHOOK_URL` | Discord webhook for proposal/run notifications | unset (disabled) |
| `GMAIL_USER` / `GMAIL_APP_PASSWORD` / `ADMIN_EMAIL` | Gmail notifications | unset (disabled) |

LLM keys are entered per-model in the Studio UI (Models page) and stored as
`key_ref`s in the DB — the API never returns or logs the key material.

## Production checklist

1. **TLS**: run behind a reverse proxy (Caddy/nginx/Traefik) terminating TLS.
2. **Auth secret**: set `AGENTFACTORY_JWT_SECRET` to a long random value.
3. **CORS**: set `AGENTFACTORY_ALLOWED_ORIGINS` to your real origin(s), not `*`.
4. **Persistence**: keep `/data` (or the SQLite path + workspace root) on a
   volume with backups.
5. **Scale**: the run worker is in-process — for heavy concurrent runs run
   multiple `uvicorn --workers N` processes (SQLite handles concurrent
   writers via WAL; see `docs/architecture.md` for the limits).
6. **Updates**: rebuild the image and restart; the DB schema migrates
   idempotently on startup (`agentfactory.app.db.init_db`).

## Troubleshooting

- **Blank UI / API-only responses**: `AGENTFACTORY_SPA_DIR` is not set or
  points at an empty directory — verify `web/dist/index.html` exists.
- **WebSocket terminal won't connect**: confirm you're behind a proxy that
  upgrades `Connection: Upgrade` for `/api/v1/workspaces/*/terminal/ws`.
- **401s after restart**: the JWT secret changed, invalidating issued tokens.
- **Permission errors on runs**: the `AGENTFACTORY_WORKSPACE_ROOT` user must
  own the directory tree.

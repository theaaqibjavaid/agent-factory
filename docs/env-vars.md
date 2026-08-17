# Environment Variables

Full reference for all `.env` variables.

## LLM API Keys

| Variable | Description | Required |
|----------|-------------|----------|
| `GEMINI_API_KEY` | Google Gemini API key (free tier) | Yes (recommended) |
| `OPENAI_API_KEY` | OpenAI API key (paid fallback) | Yes (fallback) |
| `ANTHROPIC_API_KEY` | Anthropic API key (premium fallback) | No |
| `TAVILY_API_KEY` | Tavily search API key (optional web search) | No |

## Observability

| Variable | Description | Default |
|----------|-------------|---------|
| `LANGFUSE_SECRET_KEY` | Langfuse secret key for tracing | — |
| `LANGFUSE_PUBLIC_KEY` | Langfuse public key | — |
| `LANGFUSE_HOST` | Langfuse server URL | `https://cloud.langfuse.com` |

## Repository Paths

| Variable | Description |
|----------|-------------|
| `BACKEND_PATH` | Absolute path to FastAPI backend repo |
| `FRONTEND_PATH` | Absolute path to React frontend repo |
| `ADMIN_PATH` | Absolute path to admin panel repo |

Example:
```
BACKEND_PATH=/absolute/path/to/fastapi-backend
FRONTEND_PATH=/absolute/path/to/react-frontend
ADMIN_PATH=/absolute/path/to/admin-panel
```

## Notifications

| Variable | Description |
|----------|-------------|
| `DEV_NOTIF_WEBHOOK_URL` | Discord webhook URL for approval notifications |
| `GMAIL_USER` | Gmail address for email notifications |
| `GMAIL_APP_PASSWORD` | 16-character Gmail app password |
| `ADMIN_EMAIL` | Recipient email for notifications |

## Approval Server

| Variable | Description | Default |
|----------|-------------|---------|
| `APPROVAL_SERVER_HOST` | Server bind host | `0.0.0.0` |
| `APPROVAL_SERVER_PORT` | Server port | `8000` |

## LLM Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `AGENT_DAILY_BUDGET_USD` | Daily LLM spend limit before failover stops | `5.00` |
| `LLM_TEMPERATURE` | Default temperature for LLM calls | `0.2` |

## Internal

| Variable | Description | Default |
|----------|-------------|---------|
| `AGENT_SERVER_URL` | URL for CLI `status` command to check server | `http://localhost:8000/api/agent/status` |

## Persistent Memory

| Variable | Description | Default |
|----------|-------------|---------|
| `MEMORY_DB_PATH` | Path to SQLite memory database | `~/.agentfactory/memory.db` |
| `MEMORY_AGENT_ID` | Default agent ID for memory isolation | `default` |

## JWT Authentication (Optional)

Set `JWT_SECRET_KEY` to enable JWT bearer token auth on the approval server.
Generate one with: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

When auth is enabled, all `/api/agent/*` endpoints require `Authorization: Bearer <token>`.
Mint tokens locally with `agentfactory token` — the server exposes **no** self-service
token endpoint (security hardening, Phase 0).

| Variable | Description | Default |
|----------|-------------|---------|
| `JWT_SECRET_KEY` | Secret key for signing JWT tokens | *(empty — auth disabled)* |
| `JWT_ALGORITHM` | JWT signing algorithm | `HS256` |
| `JWT_EXPIRATION_HOURS` | Token expiry in hours | `24` |
| `JWT_AUDIENCE` | Expected audience claim | `agentfactory` |
| `LOCAL_MODE` | `1` forces auth **off** even when `JWT_SECRET_KEY` is set (single-user installs) | `0` |
| `AGENT_SERVER_TOKEN` | Bearer token the background worker sends to the approval server | *(empty)* |
| `AGENTFACTORY_ALLOWED_ORIGINS` | Comma-separated CORS allowed origins (e.g. `https://app.example.com`) — used by both the approval server and the platform API | `*` (local mode) |
| `APPROVAL_DB_PATH` | Path to approval server SQLite DB | `~/.agentfactory/approval.db` |

## Platform API (Phase 1 — multi-user backend)

The platform API (`agentfactory.app.main`, mounted at `/api/v1`) is a separate
FastAPI app with its own SQLite database. It powers signup/login, workspaces,
and agents for the Studio dashboard. The v1 approval server is untouched and
keeps working in `LOCAL_MODE` (legacy bridge, Phase 1 task 1.5).

| Variable | Description | Default |
|----------|-------------|---------|
| `AGENTFACTORY_DB_PATH` | Path to the platform SQLite DB (users, workspaces, agents, ...) | `~/.agentfactory/platform.db` |
| `AGENTFACTORY_JWT_SECRET` | Signing secret for platform access JWTs (falls back to `JWT_SECRET_KEY`) | *(empty — platform auth disabled)* |
| `AGENTFACTORY_ACCESS_TOKEN_MINUTES` | Platform access-token lifetime | `15` |
| `AGENTFACTORY_REFRESH_TOKEN_DAYS` | Platform refresh-token lifetime (rotation + revocation) | `7` |
| `AGENTFACTORY_APP_URL` | Public base URL used to build OAuth redirect URIs | `http://localhost:8000` |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google OAuth app credentials (login via Google) | *(empty — disabled)* |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | GitHub OAuth app credentials (login via GitHub) | *(empty — disabled)* |

Passwords are hashed with argon2id; refresh tokens are opaque, stored in
SQLite, and rotated on every use (replays rejected). Start the platform API
with `uvicorn agentfactory.app.main:app --port 8000`.

### Runs, approvals & memory (Phase 2)

- `POST /api/v1/workspaces/{ws}/agents/{agent_id}/runs` — create a run.
  Agents with `hitl_mode=auto` start immediately; `hitl_mode=gate` creates a
  proposal and waits for `POST .../proposals/{id}/review` (approve/reject/modify).
- `GET .../runs/{run_id}/events` — SSE stream (`run.start | token | tool_call |
  tool_result | verify | memory | cost | run.end | error`, design.md §6).
- `POST .../runs/{run_id}/retry` — recover FAILED runs.
- `.../agents/{agent_id}/memory/*` — facts, history, clear (confirm `DELETE`),
  and versioned export/import bundles. Memory is scoped per workspace+agent
  inside `MEMORY_DB_PATH`.

**Destructive tools:** the runtime blocks `DESTRUCTIVE`-safety tools unless the
workspace settings JSON contains `"allow_destructive": true` (set via
`PATCH /api/v1/workspaces/{ws}`). Gated agents (`hitl_mode=gate`) are the
supported way to run destructive tasks with human approval.

### Extensibility surfaces (Phase 4)

Custom tools, skills, MCP servers, model connections, and marketplace installs
are managed through the platform API and resolved by the runtime at run time:

| Variable | Description | Default |
|----------|-------------|---------|
| `AGENTFACTORY_WORKSPACE_ROOT` | Sandbox root for custom tool code; each workspace gets a subdirectory (path-scope) | `~/.agentfactory/workspaces` |
| `AGENTFACTORY_MCP_ALLOWED_COMMANDS` | Comma-separated MCP server command allowlist (basenames) | `npx,uvx,python,python3,node,deno,bun` |

Endpoints (all workspace-scoped under `/api/v1/workspaces/{ws}`):

- `.../tools` — merged catalog (built-ins + custom + marketplace); `POST`
  creates a custom tool after validation (compile + static scan + schema
  render); `POST .../tools/validate` dry-runs the editor. Custom code runs in
  a restricted namespace (safe stdlib imports only, no subprocess/socket/eval)
  with metadata (safety/cost) taken from the registration row — never the code.
- `.../skills` — create/update/delete skills; instructions are injected into
  the system prompt of any agent that lists the skill.
- `.../mcp` — stdio/SSE server registrations with env allowlists;
  `POST .../mcp/test` probes a connection and lists its tools (hardened
  Phase 0.7 client). Commands must be in `AGENTFACTORY_MCP_ALLOWED_COMMANDS`.
- `.../models` — model connections (provider, model, base URL, `key_ref` env
  var name — keys are never stored); `POST .../models/{id}/test-call` makes a
  minimal real call. `openai_compatible`/`ollama` providers accept a `base_url`
  (OpenRouter, vLLM, LM Studio, Ollama).
- `/api/v1/marketplace` (public catalog) + `.../marketplace/install` (creates
  registrations, records an audit event with validation findings) +
  `.../marketplace/installs` (audit log).

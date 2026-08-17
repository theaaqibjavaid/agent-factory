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
| `AGENTFACTORY_ALLOWED_ORIGINS` | Comma-separated CORS allowed origins (e.g. `https://app.example.com`) | `*` (local mode) |
| `APPROVAL_DB_PATH` | Path to approval server SQLite DB | `~/.agentfactory/approval.db` |

# Approval Server

A FastAPI-based control plane that manages agent execution with human-in-the-loop approval gates.

## Overview

The approval server provides:
- **Approval gates** — Humans must approve agent actions before execution
- **SQLite state** — Full state persistence for proposals, branches, approvals
- **Discord notifications** — Send approval requests to a Discord channel
- **Gmail notifications** — Email approval requests
- **API endpoints** — RESTful interface for agent workers to poll

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/api/agent/status` | Get current agent status |
| `POST` | `/api/proposals` | Create a new proposal |
| `GET` | `/api/proposals` | List all proposals |
| `GET` | `/api/proposals/{id}` | Get a specific proposal |
| `POST` | `/api/proposals/{id}/approve` | Approve a proposal |
| `POST` | `/api/proposals/{id}/reject` | Reject a proposal |
| `GET` | `/api/branches` | List all feature branches |

## State Machine

```
IDLE → PENDING → APPROVED → EXECUTING → COMPLETED
                    ↓
                 REJECTED
```

| State | Description |
|-------|-------------|
| `IDLE` | No active work |
| `PENDING` | Proposal awaiting approval |
| `APPROVED` | Proposal approved, waiting to execute |
| `EXECUTING` | Agent is executing the proposal |
| `COMPLETED` | Execution finished |
| `REJECTED` | Proposal was rejected |

## Starting the Server

```bash
# Via CLI
agentfactory run --server-only

# Via uvicorn directly
uvicorn agentfactory.app.approval_server:app --port 8000 --reload
```

API docs available at `http://localhost:8000/docs`

## Background Worker

The worker polls the approval server for approved proposals and executes them:

```bash
# Via CLI
agentfactory run --worker-only

# Directly
python -m agentfactory.agents.worker --watch
```

## Configuration

All settings come from environment variables (see [Environment Variables](env-vars.md)):

```bash
APPROVAL_SERVER_HOST=0.0.0.0
APPROVAL_SERVER_PORT=8000
DEV_NOTIF_WEBHOOK_URL=https://discord.com/api/webhooks/...
GMAIL_USER=your-email@gmail.com
GMAIL_APP_PASSWORD=your-16-char-app-password
ADMIN_EMAIL=recipient@example.com
```

## Notifications

### Discord

Set `DEV_NOTIF_WEBHOOK_URL` to a Discord webhook URL. The server sends approval requests as embedded messages.

### Gmail

Set `GMAIL_USER`, `GMAIL_APP_PASSWORD`, and `ADMIN_EMAIL` for email notifications.

## SQLite Database

The server uses SQLite at `agentfactory.db` (configurable via `APPROVAL_DB_PATH`).

Tables:
- `proposals` — Proposal records
- `branches` — Feature branch metadata
- `approvals` — Approval log
- `notifications` — Notification history

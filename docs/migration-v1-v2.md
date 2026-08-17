# Migrating from v1 to v2 (Studio Platform)

v2 adds a multi-user **Studio platform** on top of the v1 agent SDK: signup/
login, workspaces, agent CRUD, run execution with streaming events, custom
tools, skills, MCP servers, model connections, a terminal, observability, and
autonomy guardrails. The v1 SDK (agents, tools, memory, failover) and the v1
approval server keep working unchanged — v2 is additive.

## What changed

| Area | v1 (SDK + approval server) | v2 (Studio platform) |
|------|----------------------------|----------------------|
| Auth | JWT self-mint on the approval server | Multi-user signup/login (argon2 hashes), workspace-scoped tokens |
| Agents | YAML configs + `agentfactory run` CLI | CRUD via `POST /api/v1/workspaces/{ws}/agents` + Studio UI |
| Runs | CLI/worker runs | `POST .../agents/{id}/runs` with streaming SSE events, per-agent budgets |
| Tools | Built-ins + `@tool` decorator | + custom Python tools (validated, sandboxed, env allowlist) |
| Skills | Local/pip skill loading | + Studio CRUD with dependency resolution |
| MCP | `mcp_integration.py` config | + server registry, test-connection, per-tool enablement |
| Models | `.env` LLM keys + failover chain | + per-connection models (provider/base_url/key_ref), test-call |
| Approvals | `/api/agent/*` (single-tenant) | + workspace-scoped proposals, Discord/Gmail/webhook notifications |
| Ops | — | Terminal (PTY + WS), run events, cost/token dashboards, budget alerts |
| Autonomy | — | Per-agent constitution, protected branches, path allowlists |

## Migration steps

### 1. Keep the SDK code as-is

`from agentfactory import AgentFactory`, `@tool`, `SkillRegistry`, memory, and
the failover manager are unchanged. v2 imports them under the same package.

### 2. Move agent definitions into the platform

Your YAML agents become rows in `agents`:

```bash
# Old:
#   agentfactory create-agent --name engineer --rank Senior --tools web_search

# New (API):
curl -X POST $API/api/v1/workspaces/$WS/agents \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"engineer","rank":"Senior","role_description":"...",
       "tools":["web_search"],"skills":[],"mcp_servers":[],"hitl_mode":"auto"}'
```

The Studio UI (Agents page) does the same thing. `render_agent_config()`
produces the v1-style YAML snapshot for runs, so config snapshots stay
backward compatible.

### 3. Run through the platform instead of the CLI

`POST /api/v1/workspaces/{ws}/agents/{agent_id}/runs` creates a run. In
`auto` mode it starts immediately and streams events over SSE
(`GET .../runs/{run_id}/events`); in `gate` mode it creates a proposal that
human review approves — this replaces the v1 `/api/agent/propose` flow.

### 4. Point notifications at the new config

v1 notifications used `DEV_NOTIF_WEBHOOK_URL` / Gmail env vars globally. v2
keeps those envs as fallbacks but adds per-workspace notification channels in
the Studio Settings page (Discord webhook, generic webhook, email) with
`on_run_complete` / `on_proposal` toggles.

### 5. (Optional) Move LLM keys into model connections

v1 read keys from `.env`. v2 stores model connections per workspace with
`key_ref` — the UI asks you to paste the key value when creating a connection
and only persists the reference. Provider/base_url/custom OpenAI-compatible
endpoints and Ollama are supported, and the failover pipeline is built from
your model preferences automatically.

## Rollback

Nothing is destructive: v2 writes to its own tables (`users`, `workspaces`,
`agents`, `agent_runs`, …) and leaves v1 state (`proposals`, `audit_log`, the
legacy `agentfactory.db`) untouched. Stop the v2 process and run the v1
workflow as before. If you want the v1 approval server reachable again in the
same process, keep it mounted at `/api/agent/*` (Phase 1.5 legacy bridge).

## Compatibility notes

- The legacy approval server is excluded from the v2 mypy/coverage gates; it
  is maintained separately for backward compatibility.
- `agentfactory --version` still works; the CLI is unchanged.
- v2 requires Python ≥ 3.10 and the same base dependencies as v1.

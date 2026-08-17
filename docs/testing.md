# Local Testing Guide — AgentFactory

End-to-end instructions for running and testing **every feature** locally:
the platform API, the Studio UI, the SDK/CLI, self-host Docker, and the
automated suites. Written for a fresh clone on Linux/macOS (Windows: use
Git Bash or WSL; commands are identical).

---

## 1. Prerequisites

| Tool | Version | Why |
|---|---|---|
| Python | 3.10+ | SDK + platform API |
| pip | any | Python deps |
| [Bun](https://bun.sh) | ≥ 1.0 | Studio UI (build/dev) |
| curl | any | API walkthroughs below |
| jq (optional) | any | Extract tokens from JSON in the walkthroughs |

**LLM API keys** — needed only for *real* agent runs (a fake/scripted LLM is
used by the automated tests, so tests pass without keys). Set at least one:

```bash
export GEMINI_API_KEY=...      # free tier — recommended default
# or
export OPENAI_API_KEY=...
# or
export ANTHROPIC_API_KEY=...
```

---

## 2. Install from source

```bash
git clone https://github.com/theaaqibjavaid/agent-factory.git
cd agent-factory

python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[platform,openai,anthropic]"   # or plain: pip install -e .

# Studio UI
cd web
bun install
cd ..
```

Verify the install:

```bash
agentfactory --version          # 1.2.0
python -c "import agentfactory; print(agentfactory.__version__)"   # 1.2.0
```

> From PyPI instead: `pip install agentfactory-studio`.

---

## 3. Run everything — ONE command

The whole platform (API + Studio UI) runs in a single process with a single
command. It builds the UI automatically if needed:

```bash
export AGENTFACTORY_JWT_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
agentfactory studio
```

or, equivalently: `make studio`.

Open **http://localhost:8000** — that's the Studio dashboard. Also on the
same origin: API docs at **http://localhost:8000/docs**, health at
`curl http://localhost:8000/health`.

> That's it. One process, one port, everything. `agentfactory studio`
> runs the v2 platform API (`uvicorn agentfactory.app.main:app`) and serves
> the built Studio UI from `web/dist` (building it with bun on first run).

### Optional: enable encryption-at-rest

```bash
export AGENTFACTORY_ENCRYPTION_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
# back this key up — data written with it is unrecoverable without it
```

### Alternatives (only if you want them)

- **API only** (no UI): `agentfactory studio --no-spa`
- **UI in dev mode** (hot reload; needs the API running separately on :8000):
  ```bash
  uvicorn agentfactory.app.main:app --host 0.0.0.0 --port 8000   # terminal 1
  cd web && bun run dev                                          # terminal 2 → :5173
  ```
- **Legacy v1 server** (`agentfactory run`) exists only for old SDK users —
  ignore it unless you use the pre-Phase-1 approval API.

---

---

## 5. Feature-by-feature walkthrough (API)

All examples assume the API is running on :8000 and use jq for the token.
Log in once:

```bash
BASE=http://localhost:8000/api/v1

curl -s -X POST $BASE/auth/signup -H 'Content-Type: application/json' \
  -d '{"email":"demo@example.com","password":"supersecret123","name":"Demo"}' | jq .

TOKEN=$(curl -s -X POST $BASE/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"demo@example.com","password":"supersecret123"}' | jq -r .access_token)

AUTH="Authorization: Bearer $TOKEN"

WS=$(curl -s $BASE/workspaces -H "$AUTH" | jq -r '.workspaces[0].id')
echo "workspace: $WS"
```

> A default workspace (with a starter agent and the built-in tool catalog) is
> created automatically at signup.

### 5.1 Auth

```bash
# Refresh token rotation (refresh_token returned at login)
REFRESH=$(curl -s -X POST $BASE/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"demo@example.com","password":"supersecret123"}' | jq -r .refresh_token)
curl -s -X POST $BASE/auth/refresh -H 'Content-Type: application/json' \
  -d "{\"refresh_token\":\"$REFRESH\"}" | jq .access_token

# Me
curl -s $BASE/me -H "$AUTH" | jq .

# Logout revokes the refresh token
curl -s -X POST $BASE/auth/logout -H "$AUTH" | jq .
```

### 5.2 Workspaces & members

```bash
# Create a workspace
curl -s -X POST $BASE/workspaces -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"name":"Team Alpha"}' | jq .

# Invite a member (role: owner|admin|member)
curl -s -X POST $BASE/workspaces/$WS/members -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"email":"teammate@example.com","role":"member"}' | jq .

# List members
curl -s $BASE/workspaces/$WS/members -H "$AUTH" | jq .
```

### 5.3 Agents

```bash
# Create
AGENT=$(curl -s -X POST $BASE/workspaces/$WS/agents -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"name":"Researcher","rank":"Senior","role_description":"Deep web research","hitl_mode":"auto","max_budget_usd_per_day":2.0}' | jq -r .id)
echo "agent: $AGENT"

# List + detail
curl -s $BASE/workspaces/$WS/agents -H "$AUTH" | jq .
curl -s $BASE/workspaces/$WS/agents/$AGENT -H "$AUTH" | jq .

# Rendered system prompt + tool manifest (what the engine actually runs)
curl -s $BASE/workspaces/$WS/agents/$AGENT/render -H "$AUTH" | jq .
```

### 5.4 Runs (streaming, HITL gate, retry)

**Auto mode** — starts immediately:

```bash
curl -s -X POST $BASE/workspaces/$WS/agents/$AGENT/runs -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"task":"Summarize the top 3 AI news stories"}' | jq .
```

**Stream events (SSE)** — open a second terminal:

```bash
curl -N $BASE/workspaces/$WS/runs/<RUN_ID>/events -H "$AUTH"
# events: run.start | token | tool_call | tool_result | verify | memory | cost | run.end
```

**HITL gate** — create an agent with `"hitl_mode":"gate"`, then every run
creates a proposal instead of executing:

```bash
GATED=$(curl -s -X POST $BASE/workspaces/$WS/agents -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"name":"Gated","rank":"Junior","hitl_mode":"gate"}' | jq -r .id)

PROP=$(curl -s -X POST $BASE/workspaces/$WS/agents/$GATED/runs -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"task":"Delete the temp files in /tmp/scratch"}' | jq -r .proposal_id)

# Review it (approve | reject | modify)
curl -s -X POST $BASE/workspaces/$WS/proposals/$PROP/review -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"action":"approve","notes":"go ahead"}' | jq .
```

**Retry a failed run** (e.g. a run whose LLM call failed):

```bash
curl -s -X POST $BASE/workspaces/$WS/runs/<FAILED_RUN_ID>/retry -H "$AUTH" | jq .
```

### 5.5 Memory (per workspace+agent)

```bash
# Save a fact + view history/stats
curl -s -X POST $BASE/workspaces/$WS/agents/$AGENT/memory/facts -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"key":"user_preferred_format","value":"xlsx","fact_type":"string"}' | jq .
curl -s $BASE/workspaces/$WS/agents/$AGENT/memory -H "$AUTH" | jq .

# Export → edit → re-import (versioned JSON bundle)
curl -s $BASE/workspaces/$WS/agents/$AGENT/memory/export -H "$AUTH" -o memory-bundle.json
curl -s -X POST $BASE/workspaces/$WS/agents/$AGENT/memory/import -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"bundle\": $(cat memory-bundle.json), \"mode\":\"merge\"}" | jq .

# Clear (must confirm)
curl -s -X POST $BASE/workspaces/$WS/agents/$AGENT/memory/clear -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"confirm":"DELETE"}' | jq .
```

### 5.6 Extensibility: tools, skills, MCP, models, marketplace

```bash
# Built-in + custom tool catalog (code stays server-side; metadata only)
curl -s $BASE/workspaces/$WS/tools -H "$AUTH" | jq '.tools | map(.name)'

# Create a custom tool (validated: compile + static scan + schema render)
curl -s -X POST $BASE/workspaces/$WS/tools -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"name":"greet","description":"Say hello","code":"def run(name: str) -> str:\n    return \"hi \" + name"}' | jq .

# Skills
curl -s $BASE/workspaces/$WS/skills -H "$AUTH" | jq '.skills | map(.name)'

# MCP servers (command must be in the allowlist)
curl -s -X POST $BASE/workspaces/$WS/mcp -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"name":"filesystem","transport":"stdio","command":"npx","args":["-y","@modelcontextprotocol/server-filesystem","/tmp"]}' | jq .

# Model connections (custom providers with your own keys)
curl -s $BASE/workspaces/$WS/models -H "$AUTH" | jq .

# Marketplace (browse → install → audit trail)
curl -s $BASE/marketplace -H "$AUTH" | jq '.items | map(.name)'
curl -s -X POST $BASE/marketplace/install -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"item_type\":\"tool\",\"item_id\":\"<ITEM_ID>\",\"workspace_id\":\"$WS\"}" | jq .
```

### 5.7 Terminal (WebSocket)

With the UI running, open **Studio → Terminal** and run `ls`, `pwd`, etc.
The session is pinned to the workspace root; destructive commands (rm, git
push to protected branches) trigger a **confirm prompt** first.

Programmatic check:

```bash
# The terminal is a WebSocket endpoint:
#   ws://localhost:8000/api/v1/workspaces/{workspace_id}/terminal
# Send JSON messages: {"type":"input","data":"ls\n"} | {"type":"resize","cols":80,"rows":24}
```

### 5.8 Observability

```bash
curl -s $BASE/workspaces/$WS/observability/summary -H "$AUTH" | jq .totals
curl -s $BASE/workspaces/$WS/observability/budgets -H "$AUTH" | jq '.agents'
curl -s $BASE/workspaces/$WS/observability/events -H "$AUTH" | jq '.events | length'
curl -s $BASE/workspaces/$WS/observability/alerts -H "$AUTH" | jq .
```

### 5.9 Notifications

In the UI: **Workspace → Settings → Notifications**, add a Discord webhook
URL (or Gmail app password + recipient). Then run any agent — completion and
budget-alert messages are delivered to the configured channel. The config
lives in the workspace `settings` JSON and is read at run end.

### 5.10 Encryption-at-rest (Phase 8)

```bash
# With AGENTFACTORY_ENCRYPTION_KEY set, create a gated run and inspect the DB:
sqlite3 ~/.agentfactory/platform.db "SELECT plan FROM proposals LIMIT 1;"
#   → starts with gAAAA... (ciphertext)
# The API returns the plaintext transparently:
curl -s $BASE/workspaces/$WS/proposals -H "$AUTH" | jq '.proposals[0].plan'
```

Negative test: stop the server, unset the key, restart — reads of encrypted
rows raise a clear error instead of silently returning garbage.

### 5.11 Rate limiting (Phase 7)

```bash
export AGENTFACTORY_RATE_LIMIT_AUTH=3   # restart the API
for i in 1 2 3 4; do curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  $BASE/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"demo@example.com","password":"wrong"}'; done
# 401, 401, 401, 429 (with Retry-After header)
```

---

## 6. Studio UI walkthrough

With the API on :8000 and the UI on :5173:

1. **Sign up** — first account owns the default workspace.
2. **Dashboard** — workspace overview, run counts, spend, alerts.
3. **Agents** — create/edit agents (rank, role, tools, skills, MCP servers,
   budget, HITL mode auto/gate); view the rendered config.
4. **Run an agent** — pick a task; watch the live event stream
   (tokens, tool calls, verification, cost) in the runs view.
5. **Approvals** — with a gated agent, run a task → it lands in the
   Approvals inbox → approve/reject/modify → execution starts.
6. **Memory** — inspect history/facts for any agent; export/import bundles;
   clear with confirmation.
7. **Tools / Skills / MCP / Models** — browse the catalogs, add custom tools
   (paste code → validated), register MCP servers, connect model providers.
8. **Marketplace** — install shared tools/skills; the audit trail shows who
   installed what and whether validation passed.
9. **Terminal** — workspace-scoped shell with destructive-command confirm.
10. **Observability** — run logs, cost/token dashboards, budget alerts.
11. **Settings** — profile, theme/fonts, notifications, workspace members.

---

## 7. CLI + SDK smoke

```bash
# CLI
agentfactory init            # writes .env template
agentfactory create-agent research --rank Senior
agentfactory list-tools

# SDK (scripted, no API keys needed for a hello world)
python - <<'PY'
from agentfactory.memory import PersistentMemory
m = PersistentMemory(agent_id="demo")
m.save_fact("hello", "world")
print("fact:", m.load_fact("hello"))
PY
```

---

## 8. Docker self-host

```bash
docker build -t agentfactory .
docker run -d --name af -p 8000:8000 \
  -e AGENTFACTORY_JWT_SECRET="$(openssl rand -hex 32)" \
  -e AGENTFACTORY_ENCRYPTION_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
  -v af-data:/data agentfactory
# open http://localhost:8000 — the API serves the built Studio
```

Prebuilt images publish to Docker Hub on `v*` tags once
`DOCKERHUB_USERNAME`/`DOCKERHUB_TOKEN` secrets are added
(`.github/workflows/docker.yml`).

---

## 9. Automated test suites (run from repo root)

```bash
# Backend: 229 tests, coverage gate ≥80% (platform surface)
python3 -m pytest tests/ -q --cov

# Typecheck (platform surface — the CI gate)
python3 -m mypy agentfactory/app agentfactory/runtime.py agentfactory/terminal.py \
  agentfactory/validation.py agentfactory/custom_tools.py \
  agentfactory/crypto.py agentfactory/redact.py \
  --follow-imports=skip --ignore-missing-imports

# Static security scans
python3 -m bandit -r agentfactory -q -ll
pip-audit -r requirements.txt

# Undefined-name lint (real bugs)
python3 -m ruff check --select F821 agentfactory tests

# Studio UI
cd web
bun tsc -b --noEmit
bun run build

# Packaging smoke (builds agentfactory_studio-1.2.0 wheel)
python3 -m build --wheel
```

The same checks run automatically on every push/tag in GitHub Actions
(`.github/workflows/ci.yml`).

---

## 10. Troubleshooting

| Symptom | Fix |
|---|---|
| API won't start / blank Studio | Unset `AGENTFACTORY_JWT_SECRET`? Set it. Check `curl :8000/health`; run `python3 -m pytest tests/ -q` to rule out code errors |
| UI can't reach the API | Vite proxies to `localhost:8000` — start the API first, or set `VITE_API_PROXY_TARGET` |
| 401s from the Studio | Re-login; access tokens last 15 min, refresh rotates |
| `pip install` misses a feature | Install the extra: `pip install "agentfactory-studio[platform]"` |
| Encrypted DB won't read | `AGENTFACTORY_ENCRYPTION_KEY` must match the key used at write time |
| Legacy API vs platform | `agentfactory run` = v1 approval server; `uvicorn agentfactory.app.main:app` = v2 platform |
| Tests fail with coverage <80% | `--cov` without pyproject config omits the legacy scope — use plain `pytest --cov` |

# Phases — AgentFactory Platform Roadmap

Execution plan from **audit fixes** to the full **Studio platform**. Each phase has scope, key files, deliverables, exit criteria, and effort. Phases are sequential; 0–2 are backend, 3 is the first UI.

Legend — effort: **S** ≤ 2 days, **M** ≤ 1 week, **L** ≤ 2 weeks, **XL** > 2 weeks.

---

## Phase 0 — Audit Fixes (stabilize the core)

**Goal:** eliminate every confirmed bug before building on top.

| Task | Files | Detail | Effort |
|---|---|---|---|
| 0.1 `_mcp_clients` init | `base_agent.py` | Initialize `self._mcp_clients = {}` in `__init__`; `close()` iterates it safely; add regression test for `close()` + `_ensure_mcp_tools()` with and without `mcp_configs` | S |
| 0.2 naive/aware datetimes | `base_agent.py` | `start_time`/`end_time` default to `datetime.now(timezone.utc)`; test `duration_seconds` before and after a run | S |
| 0.3 worker import bug | `agents/worker.py` | Import `RunnableAgent` (top-level); remove duplicate agent construction; test `_execute_proposal` path with a mocked server | S |
| 0.4 memory duplication | `base_agent.py` + `memory.py` | `_save_persistent_history()` saves **only new messages** (track last-saved seq); add dedupe test (saving 1,2,3 messages → 3 rows); add `save_history(..., dedupe=True)` or replace semantics | M |
| 0.5 auth hardening | `app/approval_server.py` | Remove/disable self-mint `/api/agent/token` unless explicitly enabled; require auth on propose/review/executed/delete when `JWT_SECRET_KEY` set; add `LOCAL_MODE` escape hatch for single-user installs; add auth tests | M |
| 0.6 proposal ID + CORS + startup hook | `app/approval_server.py` | UUID or `uuid4`-suffixed proposal ids (kill same-second collision); CORS: explicit origins config, drop credentials+wildcard combo; replace `@app.on_event("startup")` with lifespan; deprecation-clean | S |
| 0.7 MCP client hardening | `mcp_integration.py` | Spec-compliant framing (Content-Length) with newline fallback; unique request ids + correlation; read timeouts; notification handling; correct `args_schema` from `input_schema` | M |
| 0.8 packaging | `pyproject.toml`, `requirements.txt`, CI | `license = "MIT"` (SPDX string) or `license-files`; `requires-python` guard; verify `pip install .` builds a real wheel and `agentfactory` console script works; add `python -m build` + `pip install` gate to CI; reconcile `requirements.txt` (generate from pyproject or pin dev separately) | M |
| 0.9 repo hygiene | root, docs | Move `context.md`/planning artifacts to `docs/planning/` or archive; rewrite stale `docs/AUDIT.md` → point to this doc's Phase 0; fix README branding/links; add `CONTRIBUTING.md` | S |

**Exit criteria:** all tests green (existing 56 + new regressions for 0.1–0.5); `pip install .` yields a valid wheel; `bandit` clean on changed files; no stuck-`APPROVED` path.

---

## Phase 1 — Platform Backend: Auth, Workspaces, Data Model

**Goal:** multi-user foundation; SDK keeps working (no workspace → default workspace).

- **1.1 Schema v2** — SQLite migrations (`app/db.py` + Alembic-lite or raw `CREATE TABLE IF NOT EXISTS`): `users`, `workspaces`, `workspace_members`, `agents`, `agent_runs`, `proposals` (workspace_id), `tool/skill/mcp/model registrations`, `user_settings`. Keep v1 tables for backward compat.
- **1.2 Auth** — signup/login/refresh/oauth (Google/GitHub); argon2id; JWT access/refresh with rotation; `GET /api/v1/me`; revoke.
- **1.3 Workspace middleware** — `workspace_id` resolution + membership check on all `/api/v1/workspaces/{id}/*`; RBAC owner/admin/member.
- **1.4 Default workspace** — created at signup with one starter agent + seeded built-in tool/skill catalog.
- **1.5 Legacy bridge** — v1 endpoints keep working in `LOCAL_MODE`; in platform mode they are gated behind auth (Phase 0.5).

**Files:** new `agentfactory/app/` package: `auth.py`, `db.py`, `routers/{auth,workspaces,members}.py`, `middleware.py`; `config.py` additions (origins, mode, secret).
**Effort:** L. **Exit:** signup→login→create agent row→list agents round-trip via API; cross-tenant test passes (user B 403 on user A workspace); SDK tests unaffected.

---

## Phase 2 — Agent Engine v2

**Goal:** agents-as-data, streaming, HITL control, memory as a product feature.

- **2.1 Agents CRUD + prompt builder** — render DB agent config → system prompt + tool manifest (reuse `_build_system_prompt` logic); config snapshots per run.
- **2.2 Streaming runtime** — `AgentRuntime.run()` yields SSE events (`design.md` §6) using `FailoverLLMManager.generate_streaming` + native `tool_calls`; keep verifier loop; stop endpoint.
- **2.3 HITL toggle** — per-agent `hitl_mode`: `auto` (run immediately) vs `gate` (proposal → Approvals inbox → worker executes); wire `proposals` to workspace + agent.
- **2.4 Memory service** — scope `PersistentMemory` by workspace+agent; export/import JSON (versioned bundle); clear with confirmation; fix duplication (0.4) first.
- **2.5 Budgets & safety gates** — runtime enforcement of `max_budget_usd_per_day` (already in manager) surfaced per run; `SafetyLevel` enforcement: DESTRUCTIVE requires approval unless workspace toggle allows.
- **2.6 Worker v2** — per-workspace worker with retry/backoff, `FAILED` state recovery, no stuck rows; optional webhook events (Discord/Gmail reuse).

**Files:** `agentfactory/app/routers/{agents,runs,memory,proposals}.py`, `agentfactory/runtime.py` (new), `memory.py`, `worker.py`.
**Effort:** XL. **Exit:** end-to-end streamed run from API with tool calls + verification + cost; HITL gate flow works; memory export/import round-trips; 1000-turn history doesn't grow the DB quadratically.

---

## Phase 3 — Studio UI (dashboard)

**Goal:** the user-visible product. Stack: React + TypeScript + Vite + Tailwind + shadcn/ui (Freebuff web conventions); SSE via `fetch` stream reader; xterm.js for terminal (Phase 5 wiring).

- **3.1 App shell** — sidebar nav (Dashboard, Agents, Tools, Skills, MCP, Memory, Models, Approvals, Terminal, Settings), workspace switcher, auth pages (split-screen per `design.md`).
- **3.2 Dashboard** — stats, recent runs (live), pending approvals, onboarding checklist.
- **3.3 Agent list + editor** — wizard (3 steps), prompt preview, run console with streaming transcript + tool-call timeline + verification report + cost meter.
- **3.4 Memory UI** — facts table, history transcript, export/import, clear.
- **3.5 Models UI** — provider connect (key → secret ref), custom OpenAI-compatible endpoint, test call, failover ordering (Phase 4 wires into agents).
- **3.6 Settings** — profile, workspace, themes & fonts (token-driven, live preview).
- **3.7 Approvals inbox** — approve/modify/reject with audit history.

**Files:** `web/` (or `dashboard/`) Vite app: routes, components per `design.md` §3–4; FastAPI serves built static assets.
**Effort:** XL. **Exit:** new user signup → first agent run in < 5 min; all P0 flows in `PRD.md` reachable; Lighthouse ≥ 90 accessibility/perf on key routes; preview-ready in this repo's Freebuff environment.

---

## Phase 4 — Extensibility Surfaces: Tools, Skills, MCP, Models

**Goal:** everything installable/creatable from the UI.

- **4.1 Tool management** — catalog API + UI; custom tool editor with validation (compile + bandit-style static scan + schema render); per-agent assignment; runtime path-scope sandbox (workspace dir) + env allowlist.
- **4.2 Skills** — create wizard; built-in install; marketplace catalog API (v1: curated JSON registry; v1.1: signed manifests + GitHub/pip sources); dependency resolution (reuse `SkillRegistry`).
- **4.3 MCP management** — stdio/SSE custom servers via UI, env allowlist, command allowlist, per-tool enablement, test connection (uses hardened client from 0.7).
- **4.4 Model connections** — first-party providers + OpenAI-compatible endpoints; test-call; failover pipeline builder consumed by agent editor.
- **4.5 Marketplace shell** — browse/install flows for tools/skills/MCP; trust indicators; install audit events.

**Files:** `agentfactory/app/routers/{tools,skills,mcp,models,marketplace}.py`, `agentfactory/validation.py` (new), UI pages.
**Effort:** XL. **Exit:** install a custom tool from UI and use it in a run; create a skill in UI; connect a custom Ollama/OpenRouter model and run with it; marketplace install surfaces validation results.

---

## Phase 5 — Terminal, Observability, Autonomy

- **5.1 Terminal** — PTY backend (`pty` + WebSocket router, workspace-scoped cwd, session lifecycle, resize, reconnect, kill on disconnect); xterm.js UI; destructive-command confirmation.
- **5.2 Observability** — run logs + structured events UI; cost/token dashboards per agent/workspace; Langfuse/OTel hooks retained; budget alerts at 80%/100%.
- **5.3 Autonomy extras** — constitutional rules per agent with tool-level guards where feasible (branch protection, path allowlists); run recovery/retry UX; proposal history.
- **5.4 Notifications** — Discord/Gmail/webhook wiring for approvals + run completion (reuse `notify_tools`).

**Files:** `agentfactory/app/routers/{terminal,observability}.py`, `agentfactory/terminal.py`, UI pages.
**Effort:** L. **Exit:** terminal session works end-to-end; budget alerts fire; a gated run notifies Discord and resumes on approve.

---

## Phase 6 — Release: Packaging, CI, Docs

- **6.1 CI/CD** — GitHub Actions: lint (ruff), type check (mypy on SDK), tests (pytest + coverage ≥ 80%), security (bandit + pip-audit), wheel build + `pip install` smoke, UI build.
- **6.2 Packaging** — publish to PyPI as `agentfactory-studio` (the bare `agentfactory` name is squatted on PyPI; the import package stays `agentfactory`); `agentfactory-studio[platform]` extra for the dashboard; Dockerfile for self-host (API + static SPA + worker).
- **6.3 Docs** — update README (branding, install, quick start with Studio), `SUMMARY.md` links to all new docs, self-host guide (TLS, origins, secrets), migration guide v1→v2 schema.
- **6.4 QA** — E2E flows (signup → agent → run → memory export), security test plan from `security.md` §5, manual marketplace abuse test.

**Effort:** L. **Exit:** clean `pip install agentfactory-studio` from PyPI in a fresh env; GitHub Actions green on main; public preview runs the full P0 stack.

---

## Phase 7 — Open-Source Release Readiness

- **7.1 Security backlog** — auth rate limiting (S-8): per-IP sliding-window
  limiter on the auth surface (`429` + `Retry-After`), configurable via
  `AGENTFACTORY_RATE_LIMIT_AUTH`; regression tests.
- **7.2 Release automation** — PyPI publish workflow (trusted publishing on
  `v*` tags) with wheel smoke + published-version verification; CI now runs on
  every branch/tag plus manual dispatch; single source of truth for the
  version across SDK, platform API, and SPA (1.1.0).
- **7.3 Community** — `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md`,
  issue templates (bug/feature), PR template.
- **7.4 Docs/env** — platform env vars documented in `env-vars.md` and
  `.env.example`; Phases/SUMMARY updated.
- **7.5 Cleanup** — untracked build artifacts removed; secret scan; README
  badges.

**Exit:** everything a first-time contributor and a self-hoster need to find
is in the repo; `pip install agentfactory-studio` from PyPI works; CI is green on
`main`.

---

## Phase 8 — Security Hardening + Container Distribution

- **8.1 Encryption-at-rest (S-9)** — `agentfactory/crypto.py`: opt-in Fernet
  encryption via `AGENTFACTORY_ENCRYPTION_KEY`. Memory conversations/facts,
  run `result`/`error`, and proposal `plan`/`decision_notes` are ciphertext on
  disk and transparently decrypted for API consumers; legacy plaintext rows
  pass through with no migration. No key → unchanged behavior.
- **8.2 Log/key hygiene (S-10)** — `agentfactory/redact.py`: `redact_secrets`
  scrubs `sk-`/`AIza`/`Bearer`/`AKIA`/GitHub/Slack/JWT shapes from LLM error
  logs and persisted run errors.
- **8.3 Tool args validation (S-11)** — `validate_tool_arguments` in
  `base_tools.py`: missing/wrong-typed LLM args raise before the tool runs;
  unknown keys dropped; optional nulls allowed; MCP `input_schema`s enforced
  on `**kwargs` bridges.
- **8.4 Docker Hub publish** — `.github/workflows/docker.yml`: multi-arch
  image on `v*` tags (skips cleanly until `DOCKERHUB_USERNAME`/`TOKEN`
  secrets exist).
- **8.5 Docs/version** — bumped to 1.2.0 everywhere; CHANGELOG entry;
  `security.md` backlog S-9/S-10/S-11 marked resolved; env reference +
  self-host guide updated.

**Exit:** sensitive columns at rest are encrypted when configured (with API
round-trip + no-key-compat tests); secrets never appear in logs/errors; invalid
tool args are rejected pre-execution; container is one tag + two secrets away
from Docker Hub.

---

## Dependency Graph

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 5
   │           │           │           │
   │           └───────────┼───────────┼──────► Phase 4 (needs 0.7, 1.x, 2.1)
   └───────────────────────┴───────────┴──────► Phase 6 (after 3–5)
Phase 6 ──► Phase 7 ──► Phase 8 (hardening + Docker Hub)
```

- Phase 3 needs Phases 1–2 for the APIs it consumes.
- Phase 4 needs Phase 0.7 (MCP) + Phase 1 (registrations) + Phase 2.1 (agent wiring).
- Phase 5 terminal needs Phase 1 auth/workspace middleware.

## What ships when (MVP view)

- **First public milestone (v1.0):** Phase 0 + 1 + 2 + 3 → Studio with auth, agents, streaming runs, HITL, memory export/import, models, settings, terminal. No marketplace yet (catalog API can be stubbed).
- **v1.1:** Phase 4 (marketplace + tools/skills/MCP/model management UI) + Phase 5 observability extras.
- **v1.2:** Phase 6 polish + Docker self-host + PyPI release.

## Acceptance for the whole program

The promise from the user brief, checked off:

- [ ] Sign-up/login, profile, themes/fonts — Phase 3
- [ ] Create agents (any kind) from UI — Phase 3
- [ ] Built-in + custom tools — Phase 4
- [ ] Built-in MCP marketplace + custom MCP — Phase 4
- [ ] Install skills or create from UI — Phase 4
- [ ] Manage/export/import memory and context — Phase 2/3
- [ ] Full agentic autonomy — Phase 2/5
- [ ] Models: built-in providers (connect key) + custom provider models — Phase 4
- [ ] Human-in-the-loop on/off — Phase 2
- [ ] Support terminal — Phase 5
- [ ] `pip install` from web → create own agentic loops — Phase 0.8/6.2

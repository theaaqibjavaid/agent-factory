# PRD — AgentFactory Platform

Product Requirements Document. **Status:** Draft v0.1 (post-audit). **Owner:** Platform team. **Companion docs:** `architecture.md`, `design.md`, `security.md`, `Phases.md`.

---

## 1. Vision

> **AgentFactory is the universal, self-hostable factory for AI agents.** Anyone — from a solo developer to a team — installs one package (or opens one dashboard), signs in, and builds, runs, and owns any agent: connect any model, wire any tool, install any skill or MCP server, manage memory, and keep humans in the loop. Every capability is available from the UI *and* from Python/CLI for people who want to build their own agentic loops.

## 2. Goals (G)

- **G1** Ship a web dashboard ("Studio") where users can sign up/login and manage the full agent lifecycle: create, configure, run, monitor, and delete agents.
- **G2** Make tools, skills, and MCP extensible from the UI: use built-ins, install from a marketplace, or create/register custom ones — with validation.
- **G3** Give users full model freedom: connect first-party providers with an API key, or add any OpenAI-compatible custom endpoint.
- **G4** Make memory a user-facing asset: browse, manage, export, and import facts + history per agent.
- **G5** Support full agentic autonomy with a *user-controlled* human-in-the-loop switch (on/off per agent), budget caps, and destructive-action gates.
- **G6** Keep the product installable by anyone: `pip install agentfactory-studio` + CLI remains a first-class path; the dashboard is one optional layer.
- **G7** Personalization: themes, fonts, and profile/workspace settings.

## 3. Non-Goals (v1)

- Mobile native apps. — Multi-tenant paid billing/quota enforcement. — Visual agent-graph canvas. — Cloud-hosted multi-tenant SaaS control plane (self-host first). — Support for non-OpenAI-compatible proprietary protocols beyond the three first-party providers.

## 4. Personas

| Persona | Description | Core need |
|---|---|---|
| **Solo builder** (Aaqib class) | Builds custom agents (Excel engineer, researcher, dev agent) locally or on a VPS | Fast setup, no black boxes, full control |
| **Team operator** | Runs agents for a small team; wants approvals and budgets | HITL gates, audit trail, shared workspace |
| **Marketplace consumer** | Wants ready-made skills/tools/MCP servers | One-click install, trust indicators |
| **SDK developer** | Wants to embed agents in their own app | Clean Python API + CLI, no UI dependency |

## 5. User Stories & Functional Requirements

Priorities: **P0** (launch-blocking), **P1** (shortly after launch), **P2** (later).

### 5.1 Auth & Workspaces

| ID | Priority | Story | Acceptance criteria |
|---|---|---|---|
| FR-1 | P0 | As a user I can sign up with email+password or Google/GitHub and sign in/out. | Passwords hashed (argon2/bcrypt); session via JWT access+refresh; sign-out invalidates tokens; OAuth works for both providers. |
| FR-2 | P0 | As a user I get a default workspace and can create/rename additional workspaces. | Default workspace created on signup; workspace switcher persists per session; owner role enforced. |
| FR-3 | P1 | As an owner I can invite members with roles (owner/admin/member). | Invite via email link; role enforcement on all workspace APIs. |

### 5.2 Agents

| ID | Priority | Story | Acceptance criteria |
|---|---|---|---|
| FR-10 | P0 | As a user I can create an agent from a wizard (name, role, instructions, tools, skills, MCP, model, budget, HITL mode) and edit it later. | Agent persisted per workspace; prompt preview matches generated runtime prompt; no YAML required. |
| FR-11 | P0 | As a user I can run an agent with a task and watch a live streaming transcript with tool calls, verification, memory writes, tokens, and cost. | SSE stream delivers event types per `design.md` §6; run record saved with stats; stop works within 2 s. |
| FR-12 | P0 | As a user I can enable/disable human-in-the-loop per agent. | OFF → runs execute immediately; ON → task creates a proposal and waits; proposal decision drives execution (approve/modify/reject). |
| FR-13 | P1 | As a user I can clone an agent and pin versions of its config. | Clone copies config; config snapshots stored with runs; run shows which config it used. |
| FR-14 | P2 | As a user I can restrict an agent to a subset of its workspace's tools at runtime. | Tool restriction enforced server-side in the runtime, not just in the prompt. |

### 5.3 Tools

| ID | Priority | Story | Acceptance criteria |
|---|---|---|---|
| FR-20 | P0 | As a user I can browse built-in tools with category/safety metadata and enable them per agent. | Catalog served from registry; safety badges rendered; selection persists. |
| FR-21 | P0 | As a user I can add a custom tool by pasting `@tool` code, validate it, and assign it to agents. | Validation compiles code, renders arg schema, catches obvious sandbox violations (absolute-path writes, shell with user input) with actionable messages. |
| FR-22 | P1 | As a user I can install a tool from a marketplace listing. | Install fetches, validates, registers; source + version recorded for audit. |
| FR-23 | P1 | As a user I can toggle a per-tool sandbox scope (workspace dir only vs. unrestricted for local mode). | Paths outside scope rejected by the runtime with a clear error. |

### 5.4 Skills

| ID | Priority | Story | Acceptance criteria |
|---|---|---|---|
| FR-30 | P0 | As a user I can install a built-in skill and assign it to an agent. | Skill tools + prompt prefix merged into agent runtime; assignable from agent editor. |
| FR-31 | P0 | As a user I can create a skill in the UI (metadata + tools + prompt prefix + dependencies). | Wizard persists skill; tools validate; dependencies resolved on install. |
| FR-32 | P1 | As a user I can install a skill from the marketplace (pip package or GitHub). | Install runs in an isolated step; success/failure surfaced; skill listed with author/version. |

### 5.5 MCP

| ID | Priority | Story | Acceptance criteria |
|---|---|---|---|
| FR-40 | P0 | As a user I can register a custom MCP server (stdio or SSE) with env allowlist and test the connection. | Test lists discovered tools; failing servers reported with the actual error; per-tool enable/disable. |
| FR-41 | P1 | As a user I can browse a curated MCP marketplace and enable servers. | One-click register; trust banner shown; disabled by default until enabled. |
| FR-42 | P1 | As a user I can set per-server timeouts and see connection health. | Client enforces timeouts; health surfaced in UI. |

### 5.6 Memory

| ID | Priority | Story | Acceptance criteria |
|---|---|---|---|
| FR-50 | P0 | As a user I can view facts and history for an agent and edit/delete facts. | Facts table + history transcript; edits applied to DB immediately; delete requires confirm. |
| FR-51 | P0 | As a user I can export memory (JSON) and import it back. | Export = complete, re-importable JSON; import previews conflicts (key exists) and merges; format versioned. |
| FR-52 | P1 | As a user I can clear an agent's memory with typed confirmation. | Only that agent's memory removed; audit-logged. |
| FR-53 | P2 | As a user I can enable auto-summarization of long histories. | Summaries stored and injected when context approaches the window; no unbounded growth. |

### 5.7 Models

| ID | Priority | Story | Acceptance criteria |
|---|---|---|---|
| FR-60 | P0 | As a user I can connect Gemini / OpenAI / Anthropic by pasting an API key and test the connection. | Key stored only as a secret reference (never returned by APIs); test performs a 1-token call and shows latency/model. |
| FR-61 | P0 | As a user I can add a custom OpenAI-compatible endpoint (base URL, key, model id). | Works with Ollama/LM Studio/OpenRouter/Groq etc.; protocol = OpenAI-compatible chat completions; test call verifies. |
| FR-62 | P1 | As a user I can order models into a failover pipeline per agent and set a daily budget. | Drag-to-reorder; failover order respected at runtime; budget enforced with visible remaining spend. |

### 5.8 Approvals & Autonomy

| ID | Priority | Story | Acceptance criteria |
|---|---|---|---|
| FR-70 | P0 | As a user I can review proposals (approve/modify/reject) from the inbox and via Discord/Gmail notifications when configured. | Actions persist atomically; audit trail complete; modify supports custom instructions. |
| FR-71 | P1 | As a user I can set constitutional rules per agent (e.g., "never touch main", "no schema changes"). | Rules injected into system prompt *and* enforced by tool-level guards where feasible (branch protection, path allowlists). |
| FR-72 | P1 | As a user I can see spend/budget dashboards per agent and workspace. | Token + cost estimates from run stats; alerts at 80%/100% budget. |

### 5.9 Terminal & System

| ID | Priority | Story | Acceptance criteria |
|---|---|---|---|
| FR-80 | P0 | As a user I can open a workspace-scoped terminal in the browser. | PTY over WebSocket; resize + reconnect; session scoped to workspace sandbox; auth required. |
| FR-81 | P1 | As a user I can view worker/server status and restart a stuck run. | Status endpoint; run recovery marks failed runs (no stuck APPROVED states). |
| FR-82 | P1 | As a user I can set themes and fonts that persist. | Settings apply app-wide immediately; stored per user; dark/light/custom palettes. |

### 5.10 SDK & CLI (installable promise)

| ID | Priority | Story | Acceptance criteria |
|---|---|---|---|
| FR-90 | P0 | As a developer I can `pip install agentfactory-studio` and use the CLI + Python API without the dashboard. | Wheel builds cleanly in CI; `agentfactory init/run/list-tools/status` work; SDK does not import web dependencies. |
| FR-91 | P1 | As a developer I can drive the same agent configs from YAML or from the platform API. | Config schema shared; YAML export of an agent from the UI. |

## 6. Non-Functional Requirements

- **Performance**: agent run start latency < 1 s (post-auth); SSE first-token < 3 s; UI loads < 2 s on broadband (bundle budget ~250 KB gz JS initial).
- **Reliability**: run state machine is crash-safe (runs marked FAILED on worker death, retryable); DB writes atomic (SQLite WAL); no unbounded memory/history growth (C4 fix mandatory).
- **Security**: see `security.md` — OWASP Top 10 baseline; secrets never in client responses; per-tenant isolation tests in CI.
- **Observability**: structured logs per run/workspace; Langfuse/OTel hooks retained; cost tracking per model.
- **Portability**: Python 3.10–3.12; works fully offline/local (SQLite, no external services required except chosen LLM providers); dashboard optional.

## 7. Success Metrics

- Activation: % of new users who run their first agent within 1 hour of signup (target ≥ 60%).
- Time-to-first-agent: median < 5 minutes from signup.
- Marketplace adoption: ≥ 3 community skills/tools/MCP servers published in the first 90 days.
- Reliability: < 1% of runs end in unrecoverable state; 0 stuck-proposal bugs (C3/C4-class regressions).
- Cost control: 0 unexpected-charge incidents (budget enforcement always on).

## 8. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Tool/MCP/skill code executes arbitrary commands (RCE) in a hosted context | Critical | Workspace sandboxing, DESTRUCTIVE gates, trust banners, marketplace review process, run in least-privilege containers for hosted mode (v2) |
| JWT self-minting / open approval APIs (H1/H2) shipped as-is | Critical | Fix before any public exposure; tests assert auth required |
| Memory DB duplication (C4) degrades long-running agents | High | Deduplicate persistence; summarize; load-test with 10k-turn history |
| MCP protocol non-compliance causes hangs | High | Spec-compliant client + timeouts (H4) |
| Packaging broken (`pip install` yields empty wheel) | High | CI wheel build gate; packaging fix first (H10) |
| Scope creep into a SaaS billing platform | Medium | v1 is self-host single/multi-user; no billing |

## 9. Release Plan (summary — see `Phases.md`)

- **v1.0 (Platform)** — P0 items: Studio (auth, agents, runs), tools/skills/MCP custom management, memory export/import, models (first-party + custom), HITL, terminal, themes. Self-hosted.
- **v1.1** — P1 items: marketplace, members/roles, budgets dashboards, summarization, config versioning.
- **v2** — P2 items + hosted mode exploration.

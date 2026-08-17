# Security — AgentFactory Platform

Threat model, confirmed vulnerabilities from the audit, and the security requirements for the Studio platform. **Owner:** Platform team. **Baseline:** OWASP Top 10 (2021) + STRIDE.

---

## 1. Threat Model (STRIDE)

| # | Threat | Asset affected | Likelihood | Impact | Current status |
|---|---|---|---|---|---|
| T1 | **Spoofing** — user impersonation / forged JWT | Users, workspaces | High | High | ⚠️ Self-service token mint endpoint (H1); no real auth |
| T2 | **Tampering** — memory/history modified or corrupted | Memory DB | Medium | Medium | Plaintext SQLite; no integrity check |
| T3 | **Repudiation** — agent actions without audit trail | Repos, files, approvals | Medium | High | audit_log exists but partial (no tool-run audit, no user attribution) |
| T4 | **Info disclosure** — plans/memory/keys leaked via API or logs | Proposals, memory, secrets | High | High | ⚠️ `/api/agent/status` unauthenticated returns full plan (H2); keys at risk if logged |
| T5 | **DoS** — MCP hang, unbounded history, long LLM calls | Worker, memory DB | Medium | Medium | ⚠️ MCP no timeouts (H4); history grows unboundedly (C4); no run timeouts |
| T6 | **Elevation of privilege** — cross-workspace access | All workspace data | High | Critical | No multi-tenancy yet — must be designed in from day 1 |
| T7 | **Arbitrary code execution** via custom tools, skills, MCP servers, terminal | Host/workspace | High | Critical | By design for trusted local use; must be gated in the platform |

---

## 2. Confirmed Findings (from the audit — verified August 2026)

### 2.1 Critical

| ID | Location | Finding |
|---|---|---|
| S-1 | `app/approval_server.py` `/api/agent/token` | **Self-service JWT minting.** With `JWT_SECRET_KEY` set, any caller can POST a token with arbitrary `sub`/`roles`. With it unset, all protected endpoints run as `public`. JWT protects nothing today. |
| S-2 | `app/approval_server.py` | **Open approval surface.** `propose/review/executed/delete` are unauthenticated by default; `/api/agent/status` (unauthenticated) returns the latest proposal's full plan + blueprint. |
| S-3 | `agentfactory/tools/*` | **Unrestricted tool reach.** `write_text_file`/`delete_file`/git tools can touch any path the process can; `web_fetch`/`web_scrape_links` can hit any URL (SSRF). Fine for a trusted local CLI; **must be scoped** in a multi-tenant dashboard. |
| S-4 | `agentfactory/mcp_integration.py` | **MCP = arbitrary command execution** by configuration. A malicious/compromised `mcp.json` (or future marketplace entry) launches any `command`. No allowlist, no sandbox, no capability scoping. |
| S-5 | `agentfactory/skill.py` | Skills load and execute arbitrary Python from packages/directories — RCE by design; requires a trust model (signed/published skills, review) once a marketplace exists. |

### 2.2 High

| ID | Location | Finding |
|---|---|---|
| S-6 | `base_agent.py` | `SafetyLevel` (SAFE/MODIFIED/DESTRUCTIVE) is **never enforced**. `delete_file` defaults `confirm=True`. No gate exists for destructive tool calls. |
| S-7 | `app/approval_server.py` | CORS `allow_origins=["*"]` **with** `allow_credentials=True` — invalid combination; browsers reject credentialed requests and wildcard CORS weakens origin isolation. |
| S-8 | `app/approval_server.py` | No rate limiting on auth/approval/token endpoints; token endpoint enables credential-guessing surface when deployed. |
| S-9 | `memory.py` / `approval_server.py` | Conversations, facts, plans, and approval data stored **plaintext** in SQLite. ~~**Phase 8.1 — resolved:** opt-in Fernet encryption-at-rest via `AGENTFACTORY_ENCRYPTION_KEY` (memory content/facts, run `result`/`error`, proposal `plan`/`decision_notes`); legacy rows pass through transparently.~~ |
| S-10 | `llm_manager.py` + tools | API keys read from env at call time; key names may surface in errors/logs (e.g., Tavily fallback messages echo query; Discord errors echo responses). Audit log hygiene needed. ~~**Phase 8.2 — resolved:** `agentfactory.redact.redact_secrets` scrubs key/token shapes from logs and persisted run errors.~~ |
| S-11 | `base_tools.py` | `register_mcp_tool` stores `args_schema={"properties": metadata.__dict__}` — schema leaks internal metadata and is not a real arg schema; tool args from LLMs are unvalidated before execution. ~~**Phase 8.3 — resolved:** LLM tool args validated against the args schema before execution (missing/wrong-typed args never reach the tool); MCP `input_schema`s enforced on `**kwargs` bridges.~~ |
| S-12 | `agents/worker.py` | Worker has **no auth** — any local process can call the approval API and drive executions; no signature on worker↔server traffic. |

### 2.3 Medium

| ID | Finding |
|---|---|
| S-13 | Proposal IDs are second-resolution timestamps → collision DoS on `propose` (500). |
| S-14 | `mcp.json` committed to repo with example paths/commands; env values for MCP are stored in config (may contain tokens for some servers). |
| S-15 | No CSRF protection needed for bearer-token APIs, but cookies-based auth (future) must add CSRF tokens. |
| S-16 | `config.py` loads `.env` from cwd — a compromised cwd could swap config; validate file ownership in hosted mode. |

---

## 3. Security Requirements (target platform)

### 3.1 Authentication & Authorization (AUTH)

- **AUTH-1** Email/password with **argon2id** (or bcrypt cost ≥ 12); OAuth2 (Google, GitHub) with PKCE; refresh-token rotation with revocation.
- **AUTH-2** JWT access tokens (short-lived ≤ 15 min) + refresh tokens; `aud`, `exp`, `iat` enforced; **no self-service token minting endpoint** — tokens only issued by the auth flow.
- **AUTH-3** Remove/disable legacy `/api/agent/token`; gate legacy approval endpoints behind the same auth unless `LOCAL_MODE=1` (documented single-user mode).
- **AUTH-4** Workspace authorization middleware: every API resolves `workspace_id` from the JWT claims + membership row; cross-workspace access → 403 (tested).
- **AUTH-5** RBAC: owner/admin/member; destructive workspace ops (delete workspace, remove members, clear all memory) require owner/admin.

### 3.2 Tool, Skill & MCP Trust (EXEC)

- **EXEC-1** Workspace sandbox: tools get a scoped working directory (workspace root); absolute-path writes outside scope are rejected; `MEMORY_DB`/env allowlist enforced.
- **EXEC-2** Enforce `SafetyLevel` at runtime: `DESTRUCTIVE` tools require explicit HITL approval or a per-workspace "allow destructive" switch; `delete_file` default `confirm=False`.
- **EXEC-3** Custom tool/skill validation on upload: compile, static scan (bandit-style rules: `eval/exec`, `shell=True`, network egress to non-allowlisted hosts), schema render; reject with messages.
- **EXEC-4** MCP: spec-compliant client with timeouts; **command allowlist** (only registered binaries) and env allowlist; per-tool enablement; trust banner; marketplace entries carry signed manifest (author, version, checksum) in v1.1.
- **EXEC-5** Terminal: workspace-scoped PTY, auth-gated, session kill on disconnect; optional read-only mode.

### 3.3 Data Protection (DATA)

- **DATA-1** Secrets never stored by the app: keys live in the platform secret store / env; APIs return masked references only (`key_ref`), never values.
- **DATA-2** Optional encryption-at-rest for memory + approval DBs (SQLCipher or per-workspace key) — v1.1; at minimum, document plaintext risk and ensure DB files are outside the web root.
- **DATA-3** Export/import of memory must not include secrets; exported JSON is a signed/versioned bundle.
- **DATA-4** PII minimization: memory contents are user data — provide purge (account/workspace deletion wipes all scoped rows).

### 3.4 Transport & API Hardening (NET)

- **NET-1** TLS everywhere (self-host docs: reverse proxy + cert); HSTS recommended.
- **NET-2** CORS: explicit allowed origins per deployment (`AGENTFACTORY_ALLOWED_ORIGINS`), no wildcard with credentials.
- **NET-3** Rate limiting on auth, token, proposal, and run endpoints (per-user/IP sliding window); basic anti-brute-force lockout.
- **NET-4** Input validation: Pydantic models on every endpoint; JSON size limits; SSRF guard on `web_fetch`/`web_scrape_links` (block localhost/private ranges unless explicitly allowed).
- **NET-5** Structured, scoped logging: never log full prompts/memory/keys; log redacted events with `request_id` and `workspace_id`.

### 3.5 Integrity & Audit (AUDIT)

- **AUDIT-1** Append-only `audit_log` extended: who (user), what (action), where (workspace, agent, tool), when, request_id, outcome. Cover: auth events, agent create/edit/delete, run start/end, tool executions (name + args hash), memory export/import/clear, approval decisions, MCP connections, terminal sessions.
- **AUDIT-2** Run state machine crash-safe: FAILED/retryable states, no stuck rows (replaces polling-only behavior).

### 3.6 Dependency & Supply Chain (SUPPLY)

- **SUPPLY-1** Pin/constrain runtime deps; CI runs `pip-audit`/`pip check` on every PR.
- **SUPPLY-2** Marketplace installs run in isolated validation (no auto-exec of package code at install; load lazily after user consent).
- **SUPPLY-3** Regular `pip-audit` in CI; Dependabot/Renovate enabled.

---

## 4. OWASP Top 10 Mapping

| OWASP | Where it applies | Control |
|---|---|---|
| A01 Broken Access Control | Workspace APIs, approvals | AUTH-4/5, tests |
| A02 Cryptographic Failures | Keys, memory at rest | DATA-1/2, TLS |
| A03 Injection | YAML/skill code, terminal, git args | Validation, no `shell=True`, allowlists |
| A04 Insecure Design | Self-mint token, open approvals | S-1/S-2 fixes, threat model review |
| A05 Security Misconfiguration | CORS, debug mode, .env in cwd | NET-2, S-7, docs |
| A06 Vulnerable Components | langchain & friends | SUPPLY-1/3 |
| A07 Auth Failures | Token flows | AUTH-1/2 |
| A08 Integrity Failures | Skills/MCP marketplace, memory export | EXEC-3/4, DATA-3 |
| A09 Logging Failures | Audit trail | AUDIT-1/2 |
| A10 SSRF | web tools | NET-4 |

---

## 5. Security Test Plan (per release)

Automated coverage lives in the test suite — each item maps to the file that
enforces it. New regressions must ship a test in the same file (Phase 0 rule).

| # | Check | Automated where | Status |
|---|-------|-----------------|--------|
| 1 | Auth: signup/login/refresh/revoke, password hashing (argon2) | `tests/test_platform_api.py`, `tests/test_platform_phase2.py` | ✅ automated |
| 2 | Workspace isolation: user A cannot read user B agents/runs/memories; terminal membership (403) | `tests/test_platform_api.py`, `tests/test_platform_phase5.py::TestTerminal` | ✅ automated |
| 3 | Role enforcement: member cannot install marketplace items / manage agents | `tests/test_platform_phase6.py::TestMarketplaceAbuse` | ✅ automated |
| 4 | Custom tool gate: compile + AST static scan, banned calls (`subprocess`, `os.system`), env allowlist (nothing leaks without an allowlist) | `tests/test_platform_phase4.py` | ✅ automated |
| 5 | Marketplace abuse: bad item type, unknown item, spoofed "safe" label with dangerous code → 422 + audit-logged failure | `tests/test_platform_phase6.py::TestMarketplaceAbuse` | ✅ automated |
| 6 | MCP: command allowlist, env allowlist per server, per-tool enablement, no-timeout hang guard | `tests/test_platform_phase4.py` | ✅ automated |
| 7 | Terminal: destructive-command confirm flow, cwd pinned to workspace root (escape → 422), kill-on-disconnect | `tests/test_platform_phase5.py::TestTerminal` | ✅ automated |
| 8 | Autonomy guardrails: protected-branch push block, path allowlist enforced in `_execute_tool` | `tests/test_platform_phase5.py` | ✅ automated |
| 9 | SPA serving: path traversal cannot escape the SPA directory | `tests/test_platform_phase6.py::TestSpaServing` | ✅ automated |
| 10 | Static: `bandit -r agentfactory -ll`, `pip-audit -r requirements.txt` | `.github/workflows/ci.yml` (security job) | ✅ automated |
| 11 | Types: mypy gate on the platform surface | `.github/workflows/ci.yml` (test job) | ✅ automated |
| 12 | Encryption-at-rest (S-9): with `AGENTFACTORY_ENCRYPTION_KEY` set, memory content/facts, run result/error, and proposal plan/notes are ciphertext on disk and plaintext via the API; legacy plaintext rows still read | `tests/test_platform_phase8.py` | ✅ automated |
| 13 | Log hygiene (S-10): `redact_secrets` scrubs `sk-`/`AIza`/`Bearer`/`AKIA`/JWT shapes, leaves normal text intact; run errors redacted before persist | `tests/test_platform_phase8.py::TestRedact` + `TestRunUpdateAtRest::test_error_redacted_before_persist` | ✅ automated |
| 14 | Tool args validation (S-11): missing/wrong-typed args raise before the tool runs; MCP bridges validated; unknown keys dropped; optional nulls allowed | `tests/test_platform_phase8.py::TestArgsValidation` + `TestToolWrapperExecution` | ✅ automated |
| 15 | Dynamic/manual pre-release: run with `AGENTFACTORY_JWT_SECRET` set; fuzz proposal payloads; verify no token leaks in logs | manual checklist | ⏳ pre-release |
| 16 | Pentest checklist (before public hosting): all STRIDE items above reviewed and signed off in this file's revision log | manual checklist | ⏳ pre-release |
| 13 | Pentest checklist (before public hosting): all STRIDE items above reviewed and signed off in this file's revision log | manual checklist | ⏳ pre-release |

---

## 6. Security Backlog (ordered)

1. S-1, S-2 — real auth, remove self-mint token, gate legacy endpoints.
2. S-6 — runtime SafetyLevel enforcement + destructive gate.
3. S-7, S-8 — CORS fix, rate limiting.
4. S-3, S-4, S-5 — workspace sandbox, MCP allowlist, skill validation (EXEC-1..4).
5. ~~S-9 — encryption-at-rest option + clear docs~~ (**Phase 8.1 done**).
6. ~~S-10, S-11 — log hygiene, tool args schema validation~~ (**Phase 8.2/8.3 done**); S-12 worker auth, S-13 idempotent IDs, S-14 mcp.json hygiene, S-15 CSRF (future cookie auth), S-16 cwd .env validation remain.

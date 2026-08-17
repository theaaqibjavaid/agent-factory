# Changelog

All notable changes to AgentFactory are documented here. The format is based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.2.0] — 2026-08-17

Security hardening (Phase 8) and container distribution.

### Added

- **Encryption-at-rest** (closes S-9): set `AGENTFACTORY_ENCRYPTION_KEY` to
  encrypt memory conversations/facts, run `result`/`error`, and proposal
  `plan`/`decision_notes` before they hit SQLite. Transparently decrypted for
  API consumers; legacy plaintext rows keep working with no migration.
- **Log/key hygiene** (closes S-10): `agentfactory.redact.redact_secrets`
  scrubs `sk-`/`AIza`/`Bearer`/`AKIA`/GitHub/Slack/JWT shapes from logs and
  persisted run errors.
- **Tool arguments validation** (closes S-11): LLM-supplied tool args are
  validated against the tool's args schema before execution — missing or
  wrong-typed args never reach the tool function; MCP `input_schema`s are
  enforced on `**kwargs` bridges.
- **Docker Hub publish workflow** (`.github/workflows/docker.yml`): builds and
  pushes the self-host container on `v*` tags; skips cleanly until
  `DOCKERHUB_USERNAME`/`DOCKERHUB_TOKEN` secrets are added.

### Changed

- All version sources aligned to **1.2.0**.
- `docs/security.md` backlog: S-9/S-10/S-11 marked resolved; new automated
  checks (rows 12–14) in the security test plan.

## [1.1.0] — 2026-08-17

Open-source release hardening.

### Added

- **Rate limiting on the auth surface** (closes security backlog S-8): per-IP
  sliding-window limiter on signup/login/refresh/OAuth with a `429` +
  `Retry-After` response. Configure with `AGENTFACTORY_RATE_LIMIT_AUTH`
  (default 20 req/min/IP, `0` disables).
- **PyPI release workflow** (`.github/workflows/release.yml`) using trusted
  publishing on `v*` tags, with wheel smoke-test and published-version
  verification.
- **Community files**: `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md`,
  issue templates (bug report / feature request), and a PR template.
- CI now runs on every branch and tag, plus manual `workflow_dispatch`.

### Changed

- All version sources aligned to **1.1.0** (SDK `__version__`, platform API,
  Studio SPA).
- `docs/security.md` security test plan is now a checklist table mapping each
  check to its automated test.
- `README.md` Studio quick-start and self-host pointers; env reference
  extended with the platform variables.

## [1.0.0] — 2026-08-16

First public milestone: the Studio platform (auth, agents, streaming runs,
HITL approvals, memory, models, settings, terminal, observability) plus the
SDK (agents, tools, memory, LLM failover) from Phases 0–6.

### Added (Phases 0–6)

- **Phase 0** — audit fixes and regression tests across the SDK.
- **Phase 1** — multi-user backend: signup/login (argon2 + JWT rotation),
  workspaces, agents, roles.
- **Phase 2** — agent engine v2: run lifecycle, SSE event streaming, HITL
  gate, retries, daily USD budgets, constitution.
- **Phase 3** — Studio UI: dashboard, agent editor, runs, approvals, memory
  import/export, settings, themes.
- **Phase 4** — extensibility: custom tools (validated + sandboxed with env
  allowlists), skills (with dependency resolution), MCP servers (per-tool
  enablement), model connections (failover pipeline), marketplace with audit
  trail.
- **Phase 5** — operations: PTY terminal with destructive-command guard,
  observability (run events, cost/token dashboards, budget alerts),
  autonomy guardrails (protected branches, path allowlists), notifications
  (Discord/Gmail/webhook).
- **Phase 6** — release: expanded CI (mypy, coverage gate ≥80%, bandit,
  pip-audit, UI build), Dockerfile self-host, SPA serving, self-host +
  migration guides.

## [0.9.0] — 2026-08-14

Legacy SDK baseline: single-agent template with LLM failover, persistent
memory, tool registry, verifier, CLI, and the v1 approval server. This is the
v1 codebase that Phases 0–6 built on — see `docs/migration-v1-v2.md`.

[Unreleased]: https://github.com/theaaqibjavaid/agent-factory/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/theaaqibjavaid/agent-factory/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/theaaqibjavaid/agent-factory/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/theaaqibjavaid/agent-factory/releases/tag/v1.0.0
[0.9.0]: https://github.com/theaaqibjavaid/agent-factory/releases/tag/v0.9.0

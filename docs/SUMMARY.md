# AgentFactory Documentation

## Product & Planning

- [PRD](PRD.md) — Product Requirements Document for the AgentFactory Platform.
- [Phases](Phases.md) — Execution roadmap: Phase 0 (audit fixes) → Phase 6 (release).
- [Architecture](architecture.md) — Universal agent factory, ranked hierarchy, LLM failover pipeline, tool registry, MCP integration, platform backend.
- [Design](design.md) — Product and visual design system for the Studio dashboard.
- [Security](security.md) — Threat model, auth design, and security test plan.

## Guides

- [Installation](installation.md) — Set up your environment and API keys.
- [Quick Start](quick-start.md) — Run your first agent in 5 minutes.
- [Self-Host Studio](self-host.md) — Run the full platform (API + dashboard + terminal) in Docker or bare metal.
- [Local Testing Guide](testing.md) — Run the API + Studio UI and test every feature end to end.
- [Migrate v1 → v2](migration-v1-v2.md) — Move from the SDK/approval server to the Studio platform.
- [CLI Reference](cli-reference.md) — All CLI commands: `init`, `run`, `create-agent`, `list-tools`, `status`.

## Concepts

- [Architecture](architecture.md) — Universal agent factory, ranked hierarchy, LLM failover pipeline, tool registry, MCP integration.
- [Agent Configuration](agent-config.md) — YAML schema for defining agent teams (engineer_crew, custom configs).
- [Tool System](tools.md) — Using built-in tools, writing custom tools with the `@tool` decorator, legacy alias compatibility.
- [Persistent Memory](memory.md) — SQLite-backed fact storage and conversation history across sessions.
- [Skills](skills.md) — Skill marketplace: dynamic skill loading from packages or directories.
- [Feedback Learning](feedback-learning.md) — Agent self-improvement via learn_from_correction().
- [LLM Failover & Budgeting](llm-failover.md) — Gemini-first → OpenAI → Anthropic failover with daily USD budget control and Langfuse tracing.
- [Approval Server](approval-server.md) — FastAPI control plane: SQLite state, Discord/Gmail notifications, API endpoints.
- [Platform API](env-vars.md#platform-api-phase-1--multi-user-backend) — Phase 1 multi-user backend: signup/login, workspaces, agents (env reference).
- [MCP Integration](mcp-integration.md) — Model Context Protocol server configuration and custom tool loading.
- [Verifier](verifier.md) — Post-execution verification, context pruning for failing lines, audit reports.

## Reference

- [API Reference](api-reference.md) — Python API for `AgentFactory`, `FailoverLLMManager`, `ToolRegistry`, `Verifier`, `AgentConfig`.
- [Environment Variables](env-vars.md) — Complete `.env` reference.

## Community

- [Security Policy](../SECURITY.md) — report vulnerabilities privately; supported versions.
- [Code of Conduct](../CODE_OF_CONDUCT.md) — community standards.
- [Changelog](../CHANGELOG.md) — release history (Keep a Changelog).
- [Contributing](../CONTRIBUTING.md) — development setup, testing, contribution workflow.

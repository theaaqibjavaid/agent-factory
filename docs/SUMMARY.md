# NeuraHive Documentation

> The repository is currently undergoing the AgentFactory → NeuraHive v2 transition. The v2 architecture and roadmap are the planning source of truth.

## Product & Planning

- [NeuraHive v2 Master Roadmap](NEURAHIVE_V2_ROADMAP.md) — Complete phased roadmap, architecture boundaries, milestones, acceptance criteria, and implementation priorities.
- [NeuraHive Architecture Contract](NEURAHIVE_ARCHITECTURE_CONTRACT.md) — Architectural constitution: core/platform boundary, dependency direction, public APIs, providers, security, workflows, testing, and branch policy.
- [PRD](PRD.md) — Existing product requirements and platform scope.
- [Phases](Phases.md) — Existing execution history/roadmap for the current platform; use the NeuraHive v2 roadmap for future architecture work.
- [Architecture](architecture.md) — Current implementation architecture.
- [Design](design.md) — Product and visual design system for Studio.
- [Security](security.md) — Threat model, auth design, and security test plan.

## Guides

- [Installation](installation.md) — Current installation and environment setup.
- [Quick Start](quick-start.md) — Run the current agent stack.
- [Self-Host Studio](self-host.md) — Run the current platform in Docker or bare metal.
- [Local Testing Guide](testing.md) — Run the API + Studio UI and test the current feature set.
- [Migrate v1 → v2](migration-v1-v2.md) — Existing migration from the legacy SDK/approval-server flow to the current platform.
- [CLI Reference](cli-reference.md) — Current CLI commands.

## Concepts

- [Agent Configuration](agent-config.md) — Current YAML agent configuration.
- [Tool System](tools.md) — Current built-in/custom tool system.
- [Persistent Memory](memory.md) — Current SQLite-backed memory implementation.
- [Skills](skills.md) — Current skill loading/marketplace behavior.
- [Feedback Learning](feedback-learning.md) — Current correction-learning behavior.
- [LLM Failover & Budgeting](llm-failover.md) — Current provider failover and budget behavior.
- [Approval Server](approval-server.md) — Current approval/control-plane implementation.
- [Platform API](env-vars.md#platform-api-phase-1--multi-user-backend) — Current platform backend reference.
- [MCP Integration](mcp-integration.md) — Current MCP support.
- [Verifier](verifier.md) — Current verification implementation.

## Reference

- [API Reference](api-reference.md) — Current Python API.
- [Environment Variables](env-vars.md) — Current environment reference.

## Community

- [Security Policy](../SECURITY.md) — vulnerability reporting.
- [Code of Conduct](../CODE_OF_CONDUCT.md) — community standards.
- [Changelog](../CHANGELOG.md) — release history.
- [Contributing](../CONTRIBUTING.md) — development setup, testing rules, and PR workflow.

## Documentation Rule for v2

The **NeuraHive v2 Master Roadmap** is the source of truth for future architecture work. Each completed phase must update the roadmap, architecture contract, relevant concept/reference documentation, tests, migration notes when applicable, and changelog when user-facing.

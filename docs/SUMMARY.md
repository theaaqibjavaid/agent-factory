# AgentFactory Documentation

## Guides

- [Installation](installation.md) — Set up your environment and API keys.
- [Quick Start](quick-start.md) — Run your first agent in 5 minutes.
- [CLI Reference](cli-reference.md) — All CLI commands: `init`, `run`, `create-agent`, `list-tools`, `status`.

## Concepts

- [Architecture](architecture.md) — Universal agent factory, ranked hierarchy, LLM failover pipeline, tool registry, MCP integration.
- [Agent Configuration](agent-config.md) — YAML schema for defining agent teams (engineer_crew, custom configs).
- [Tool System](tools.md) — Using built-in tools, writing custom tools with the `@tool` decorator, legacy alias compatibility.
- [LLM Failover & Budgeting](llm-failover.md) — Gemini-first → OpenAI → Anthropic failover with daily USD budget control and Langfuse tracing.
- [Approval Server](approval-server.md) — FastAPI control plane: SQLite state, Discord/Gmail notifications, API endpoints.
- [MCP Integration](mcp-integration.md) — Model Context Protocol server configuration and custom tool loading.
- [Verifier](verifier.md) — Post-execution verification, context pruning for failing lines, audit reports.

## Reference

- [API Reference](api-reference.md) — Python API for `AgentFactory`, `FailoverLLMManager`, `ToolRegistry`, `Verifier`, `AgentConfig`.
- [Environment Variables](env-vars.md) — Complete `.env` reference.

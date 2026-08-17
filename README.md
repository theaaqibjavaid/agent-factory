# AgentFactory

[![PyPI version](https://img.shields.io/badge/PyPI-1.0.0-blue?logo=pypi)](https://pypi.org/project/agentfactory/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://www.python.org/downloads/)
[![Production Ready](https://img.shields.io/badge/Status-Production--Ready-green)](https://github.com/theaaqibjavaid/agent-factory)
[![Documentation](https://img.shields.io/badge/Docs-Ready-orange)](https://github.com/theaaqibjavaid/agent-factory/tree/main/docs)
[![Tests](https://img.shields.io/badge/Tests-201%20Passing-brightgreen)](https://github.com/theaaqibjavaid/agent-factory/actions)
[![Coverage](https://img.shields.io/badge/Coverage-84%25-yellow)](https://github.com/theaaqibjavaid/agent-factory/actions)

AgentFactory is a universal, open-source Python SDK — and a full Studio platform — for building and operating production-grade AI agents of any type.

A single `pip install agentfactory[platform]` gives you the SDK (LLM failover, persistent memory, native tool calling, streaming, skill marketplace, human-in-the-loop approvals) **plus** a multi-user Studio: sign up, build agents with custom tools/skills/MCP servers, run them with full observability, and operate them from a built-in terminal.

---

## Studio (self-hosted dashboard)

```bash
# SDK + platform extra (API server), then build the UI and run one process:
pip install 'agentfactory[platform]'
cd web && bun install && bun run build && cd ..
AGENTFACTORY_SPA_DIR="$(pwd)/web/dist" AGENTFACTORY_JWT_SECRET="$(openssl rand -hex 32)" \
  uvicorn agentfactory.app.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`, sign up, and you get: agents (constitution +
guardrails), custom tools (validated + sandboxed with env allowlists), skills
(with dependency resolution), MCP servers (per-tool enablement), model
connections (bring-your-own key), a marketplace, a PTY terminal, cost/token
dashboards with budget alerts, and Discord/Gmail/webhook notifications.

Docker one-liner and the production checklist: [docs/self-host.md](docs/self-host.md).
Migrating an existing v1 deployment: [docs/migration-v1-v2.md](docs/migration-v1-v2.md).

---

## Key Features

| Feature | Description |
|---------|-------------|
| Universal Template | Powers any agent type engineers, researchers, analysts, assistants |
| LLM Failover Pipeline | Gemini (free) to OpenAI to Anthropic with USD budget control |
| Persistent Memory | SQLite-backed conversation history + key-value facts across sessions |
| Streaming LLM Output | Real-time async generators for text and tool calls |
| Native Tool Calling | LangChain bind_tools() integration |
| Skill Marketplace | Dynamic skill loading from pip packages or local directories |
| MCP Integration | Model Context Protocol server discovery and tool registration |
| JWT Authentication | Production-grade auth on the approval server |
| Feedback Learning | learn_from_correction() for agent self-improvement |
| Human-in-the-Loop | FastAPI approval server with Discord/Gmail notifications |
| Safety Levels | @tool decorator with SAFE / MODIFIED / DESTRUCTIVE classification |
| Studio Platform | Multi-user API + dashboard: agents, runs, tools, skills, MCP, models |
| Custom Tools | Validated Python tools in a sandbox with per-tool env allowlists |
| Terminal | PTY shell in the browser with destructive-command confirmation |
| Observability | Run events, cost/token dashboards, daily budget alerts (80%/100%) |
| Autonomy Guardrails | Per-agent constitution, protected branches, path allowlists |
| Marketplace | Curated tools/skills/MCP catalog with trust indicators + audit trail |
| Production Packaging | PEP 561 compliant, pyproject.toml, CLI entry points, Dockerfile |

---

## Installation

```
pip install agentfactory
```

Optional: pip install agentfactory[all] for all LLM providers.

---

## Quick Start

```
cp .env.example .env
# Edit .env with your API keys

agentfactory init
agentfactory run
```

---

## Programmatic Usage

```
from agentfactory import AgentFactory, Skill

factory = AgentFactory()
agent = factory.create_agent("Senior")
result = await agent.run("Implement user authentication")
```

---

## Documentation

Full index: docs/SUMMARY.md

- Self-Host Studio: docs/self-host.md
- Migrate v1 → v2: docs/migration-v1-v2.md
- Architecture: docs/architecture.md
- Quick Start: docs/quick-start.md
- CLI Reference: docs/cli-reference.md
- Persistent Memory: docs/memory.md
- Skills: docs/skills.md
- LLM Failover: docs/llm-failover.md
- Approval Server: docs/approval-server.md
- MCP Integration: docs/mcp-integration.md
- Feedback Learning: docs/feedback-learning.md
- API Reference: docs/api-reference.md
- Environment Variables: docs/env-vars.md
- Production Audit: docs/AUDIT.md
- Security (incl. test plan): docs/security.md

---

## License

MIT

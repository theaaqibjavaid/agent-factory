# AgentFactory

[![PyPI version](https://img.shields.io/badge/PyPI-1.0.0-blue?logo=pypi)](https://pypi.org/project/agentfactory/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://www.python.org/downloads/)
[![Production Ready](https://img.shields.io/badge/Status-Production--Ready-green)](https://github.com/agentfactory/agentfactory)
[![Documentation](https://img.shields.io/badge/Docs-Ready-orange)](https://docs.agentfactory.ai)
[![Tests](https://img.shields.io/badge/Tests-56%20Passing-brightgreen)](https://github.com/agentfactory/agentfactory/actions)

AgentFactory is a universal, open-source Python SDK for building production-grade AI agents of any type.

A single pip install gives you LLM failover, persistent memory, native tool calling, streaming, skill marketplace, and human-in-the-loop approvals.

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
| Production Packaging | PEP 561 compliant, pyproject.toml, CLI entry points |

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

---

## License

MIT

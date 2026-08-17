<p align="center">
  <h1 align="center">AgentFactory</h1>
  <p align="center">The universal AI agent factory — a Python SDK <em>and</em> a self-hosted Studio for building, running, and operating any AI agent.</p>
  <p align="center">
    <a href="https://pypi.org/project/agentfactory-studio/"><img src="https://img.shields.io/pypi/v/agentfactory-studio?logo=pypi" alt="PyPI version"></a>
    <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"></a>
    <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.10%2B-blue?logo=python" alt="Python 3.10+"></a>
    <a href="https://github.com/theaaqibjavaid/agent-factory/actions"><img src="https://github.com/theaaqibjavaid/agent-factory/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
    <a href="https://github.com/theaaqibjavaid/agent-factory/actions"><img src="https://img.shields.io/badge/Coverage-85%25-yellow" alt="Coverage"></a>
    <a href="https://github.com/theaaqibjavaid/agent-factory/blob/main/docs/SUMMARY.md"><img src="https://img.shields.io/badge/Docs-Summary-orange" alt="Docs"></a>
    <a href="https://github.com/theaaqibjavaid/agent-factory/blob/main/CODE_OF_CONDUCT.md"><img src="https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg" alt="Code of Conduct"></a>
  </p>
</p>

AgentFactory is a configuration-driven **Agent OS**: instead of writing a new
codebase for every agent you need, you define an agent's identity, tools, and
rules as data and the same engine brings it to life — a software engineer, a
research analyst, a customer assistant, anything.

- **SDK** — one `pip install` gives you LLM failover, persistent memory, native
  tool calling, streaming, skills, MCP, and human-in-the-loop approvals.
- **Studio** — a self-hosted multi-user dashboard: sign up, build agents,
  install tools/skills/MCP servers, run with full observability, and operate
  from a built-in terminal.

---

## Table of Contents

- [✨ Features](#-features)
- [🚀 Quick Start](#-quick-start)
- [🧩 SDK Usage](#-sdk-usage)
- [🖥️ CLI Reference](#️-cli-reference)
- [🏗️ Architecture](#️-architecture)
- [🛡️ Security](#️-security)
- [📚 Documentation](#-documentation)
- [🤝 Contributing](#-contributing)
- [📄 License](#-license)

---

## ✨ Features

**Engine**

| | |
|---|---|
| 🧠 **Universal agent template** | One engine, any agent — identity, tools, and rules are configuration, not code |
| 🔁 **LLM failover pipeline** | Gemini → OpenAI → Anthropic with per-call failover and USD budget control |
| 💾 **Persistent memory** | SQLite-backed conversation history + key-value facts, export/import bundles |
| ⚡ **Streaming output** | Async generators for text and tool calls |
| 🛠️ **Tool system** | Built-ins, `@tool` decorator, and validated custom Python tools in a sandbox |
| 🧩 **Skill marketplace** | Load skills from packages, directories, or the Studio marketplace |
| 🔌 **MCP support** | Model Context Protocol servers with command/env allowlists and per-tool toggles |
| ✅ **Verifier** | Post-execution checks with failing-line context pruning and audit reports |
| 📚 **Feedback learning** | `learn_from_correction()` for continuous self-improvement |

**Studio platform**

| | |
|---|---|
| 👥 **Multi-user auth** | Signup/login (argon2id), JWT rotation, workspaces, roles |
| 🤖 **Agent studio** | Build agents with constitution rules and autonomy guardrails |
| 🚀 **Streaming runs** | SSE event stream per run, retries, per-agent daily budgets |
| ✋ **Human-in-the-loop** | Gate mode, proposal inbox, Discord/Gmail/webhook notifications |
| 🧪 **Custom tools** | Compile + AST-validated code with per-tool env allowlists |
| 🏪 **Marketplace** | Curated tools/skills/MCP catalog with trust indicators + audit trail |
| 📊 **Observability** | Run events, cost/token dashboards, budget alerts (80% / 100%) |
| 🖥️ **Terminal** | In-browser PTY shell with destructive-command confirmation |
| 🛡️ **Guardrails** | Protected branches, path allowlists, constitutional rules |

---

## 🚀 Quick Start

### Option A — Self-host the Studio (full experience)

**One command, one process, one port:**

```bash
pip install 'agentfactory-studio[platform]'   # or: pip install -e .
agentfactory studio                            # builds the UI if needed
```

Open **http://localhost:8000** — that's the Studio: sign up, create an agent,
add tools/skills/MCP servers and a model connection with your own API key, run
a task, and watch it stream — with approvals, memory, terminal, and full
observability. API docs: http://localhost:8000/docs.

```bash
# …or Docker (one container serves API + UI + worker)
docker build -t agentfactory .
docker run -d -p 8000:8000 \
  -e AGENTFACTORY_JWT_SECRET="$(openssl rand -hex 32)" \
  -v agentfactory-data:/data \
  agentfactory
```

> **PyPI note:** the distribution publishes as `agentfactory-studio` because the
> bare `agentfactory` name is squatted on PyPI (placeholder `0.0.0` release by
> another author). The Python import package remains `agentfactory`. Until the
> first PyPI release, install from source:
> `pip install git+https://github.com/theaaqibjavaid/agent-factory.git`.

### Option B — SDK only

```bash
pip install agentfactory-studio[all]   # all LLM providers
agentfactory init
agentfactory run
```

> `agentfactory run` is the **legacy v1** approval server. For the current
> platform use `agentfactory studio`.

See [docs/quick-start.md](docs/quick-start.md), [docs/testing.md](docs/testing.md),
and [docs/self-host.md](docs/self-host.md).

---

## 🧩 SDK Usage

```python
import asyncio
from agentfactory import AgentFactory

async def main():
    factory = AgentFactory()
    agent = factory.create_agent("Senior")
    result = await agent.run("Implement user authentication")
    print(result)

asyncio.run(main())
```

Custom tools, skills, MCP servers, and memory integrate through the registry —
see the [API reference](docs/api-reference.md) and [tool system](docs/tools.md).

---

## 🖥️ CLI Reference

| Command | Description |
|---|---|
| `agentfactory init` | Scaffold a project + `.env` |
| `agentfactory run` | Run the default agent |
| `agentfactory create-agent` | Add an agent profile |
| `agentfactory list-tools` | List registered tools |
| `agentfactory status` | Check the approval server |
| `agentfactory token` | Mint a local JWT (v1 approval server) |

Full reference: [docs/cli-reference.md](docs/cli-reference.md).

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                        Studio (web/)                           │
│  Dashboard · Agent editor · Tools/Skills/MCP · Terminal ·      │
│  Observability · Approvals · Settings                          │
└──────────────────────────────┬─────────────────────────────────┘
                               │ HTTP / SSE / WebSocket
┌──────────────────────────────▼─────────────────────────────────┐
│                 Platform API (agentfactory/app)                │
│  Auth · Workspaces · Agents · Runs · Proposals · Memories ·    │
│  Tools · Skills · MCP · Models · Marketplace · Terminal ·      │
│  Observability        (SQLite, argon2id, JWT rotation)         │
└──────────────────────────────┬─────────────────────────────────┘
                               │ in-process worker + run broker
┌──────────────────────────────▼─────────────────────────────────┐
│                    Runtime (agentfactory/runtime.py)            │
│  LLM failover · tool sandbox · skills · MCP attach ·           │
│  constitution · guardrails · budget alerts · notifications     │
└────────────────────────────────────────────────────────────────┘
```

More: [docs/architecture.md](docs/architecture.md), [docs/design.md](docs/design.md).

---

## 🛡️ Security

Security is a first-class concern: argon2id password hashing, JWT rotation
with revocation, per-IP rate limiting on auth, **opt-in encryption-at-rest**
(set `AGENTFACTORY_ENCRYPTION_KEY` to encrypt conversations, facts, plans, and
approval data), validated + sandboxed custom tool execution with schema-validated
tool arguments, MCP command/env allowlists, destructive-command guards, path
allowlists, secret-scrubbed logs, and an automated security pipeline (bandit,
pip-audit, mypy, coverage gate) in CI.

- Threat model + test plan: [docs/security.md](docs/security.md)
- Reporting vulnerabilities: [SECURITY.md](SECURITY.md)

---

## 📚 Documentation

Full index: [docs/SUMMARY.md](docs/SUMMARY.md)

| Area | Doc |
|---|---|
| 🏠 Self-hosting (Docker, env vars, TLS) | [docs/self-host.md](docs/self-host.md) |
| 🔄 Migrating v1 → v2 | [docs/migration-v1-v2.md](docs/migration-v1-v2.md) |
| 🧠 Architecture | [docs/architecture.md](docs/architecture.md) |
| 🚀 Quick start | [docs/quick-start.md](docs/quick-start.md) |
| 🛠️ Tools & skills | [docs/tools.md](docs/tools.md) · [docs/skills.md](docs/skills.md) |
| 🔌 MCP | [docs/mcp-integration.md](docs/mcp-integration.md) |
| 🔁 LLM failover | [docs/llm-failover.md](docs/llm-failover.md) |
| 💾 Memory | [docs/memory.md](docs/memory.md) |
| 📡 API reference | [docs/api-reference.md](docs/api-reference.md) |
| ⚙️ Environment variables | [docs/env-vars.md](docs/env-vars.md) |

---

## 🤝 Contributing

We welcome contributions of all kinds — code, docs, issues, and feedback.

- [CONTRIBUTING.md](CONTRIBUTING.md) — dev setup, testing rules, PR workflow
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — community standards
- [CHANGELOG.md](CHANGELOG.md) — release history
- [SECURITY.md](SECURITY.md) — reporting vulnerabilities

Every PR runs the full gate in CI: tests + coverage ≥ 80%, mypy, ruff,
bandit, pip-audit, and the Studio build.

⭐ If AgentFactory helps you build something, star the repo — it tells us the
work matters and helps others find it.

---

## 📄 License

[MIT](LICENSE) © 2026 AgentFactory Contributors

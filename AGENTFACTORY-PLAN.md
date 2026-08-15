# AgentFactory — Universal AI Agent Template

## PLAN DOCUMENT

> Phase 1: Architecture & Planning

---

## Executive Summary

AgentFactory is a **universal, configuration-driven Python framework** that lets anyone create custom AI agents of any type — from personal engineering teams to Excel specialists to research assistants. It's designed to be:

- **Clonable**: Anyone forks the repo and gets a working agent framework immediately
- **Extensible**: Add new tools via decorators, support both built-in and MCP (Model Context Protocol) tools
- **Ranked**: Agents have hierarchy (Senior, Junior, QA, Manager) with strict role boundaries
- **Safe**: Branch protection, approval gates, budget controls, verification loops
- **Open source ready**: `.env.example`, comprehensive tests, clean architecture, MIT license

---

## Phase 1: Architecture & Directory Structure

### Directory Layout (GitHub-ready)

```
agentfactory/
├── .github/                    # GitHub workflows + issue templates
│   ├── workflows/
│   │   ├── ci.yml              # Tests on push/PR
│   │   └── release.yml         # Release on tag
│   └── ISSUE_TEMPLATE/
│       ├── feature_request.md
│       └── bug_report.md
├── .gstack/                    # Local dev environment (gitignored)
├── factory/                    # Core template layer (universal)
│   ├── __init__.py
│   ├── llm_manager.py         # LLM failover: free→paid tiers, budget control
│   ├── base_agent.py          # AgentFactory: create any agent from config
│   ├── base_tools.py          # @tool decorator + built-in tools registry
│   ├── mcp_integration.py     # MCP client: marketplace + custom tools
│   ├── verifier.py            # Post-execution verification framework
│   └── config.py              # Pydantic settings + environment loading
├── agents/                     # Example agent configurations
│   ├── __init__.py
│   ├── config_loader.py       # YAML profile loader
│   ├── examples/              # Example agent configs
│   │   ├── engineer_crew.yaml
│   │   ├── excel_agent.yaml
│   │   └── researcher_agent.yaml
│   └── worker.py              # Background worker (polls for approvals)
├── app/                        # FastAPI control plane (optional)
│   ├── __init__.py
│   └── approval_server.py     # Approval API + Discord/Gmail/webhook
├── tools/                      # Plugin tool directory (user can add custom tools)
│   ├── __init__.py
│   ├── git_tools.py           # Git operations (branch, commit, push)
│   ├── web_tools.py           # Web research, browsing
│   ├── file_tools.py          # File read/write/analyze
│   └── notify_tools.py        # Discord, Gmail, webhook notifications
├── tests/                      # Comprehensive test suite (25+ tests)
│   ├── __init__.py
│   ├── conftest.py            # Pytest fixtures
│   ├── test_llm_manager.py
│   ├── test_base_agent.py
│   ├── test_base_tools.py
│   ├── test_mcp_integration.py
│   ├── test_verifier.py
│   ├── test_config.py
│   ├── test_config_loader.py
│   ├── test_worker.py
│   └── test_approval_server.py
├── docs/                       # Architecture & usage docs
│   ├── ARCHITECTURE.md
│   ├── CUSTOM_TOOLS.md
│   ├── MCP_INTEGRATION.md
│   ├── CREATING_AGENTS.md
│   └── EXAMPLES.md
├── scripts/                    # Utility scripts
│   └── setup.py               # Install script for new users
├── mcp.json                    # Local configuration sandbox for MCP servers (gitignored)
├── agentfactory/cli.py         # CLI entry point: init, run, create-agent
├── .env.example                # Template for environment variables
├── .gitignore
├── LICENSE                     # MIT
├── README.md                   # Main documentation
├── requirements.txt
├── requirements-dev.txt        # Dev/test dependencies
├── pyproject.toml              # Package metadata
└── pytest.ini                  # Test config
```

---

## Core Architecture

### 1. Factory Layer (`factory/`)

The base framework that anyone can use to create agents:

```
┌─────────────────────────────────────────────────────┐
│                    AgentFactory                      │
│    (Universal, configuration-driven, clonable)      │
├─────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │ LLM Manager │  │ Base Agent  │  │ Verifier    │  │
│  │ - Failover  │  │ - Config    │  │ - Audit     │  │
│  │ - Budget    │  │ - Tools     │  │ - Reports   │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  │
│                                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │ Base Tools  │  │ MCP Client  │  │ Config      │  │
│  │ - @tool     │  │ - Auto-disc.│  │ - Settings   │  │
│  │ - Registry  │  │ - Marketplace│  │ - Env vars   │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  │
└─────────────────────────────────────────────────────┘
```

### 2. Tools System

**Built-in tools** live in `tools/` with `@tool` decorator registration.
**MCP tools** can be loaded from:

- MCP marketplace servers (installed via MCP config)
- Custom MCP servers (user-defined JSON/YAML in `mcp_servers/`)
- Local Python tools (via `@tool` decorator in `tools/`)

### 3. Agent Hierarchy

| Rank    | Can Delegate | Can Write Code | Can Review | Can Propose | Purpose                         |
| ------- | ------------ | -------------- | ---------- | ----------- | ------------------------------- |
| Manager | ✅           | ✅             | ✅         | ✅          | Oversees team, manages workflow |
| Senior  | ✅           | ✅             | ✅         | ✅          | Plans, designs, proposes        |
| Junior  | ❌           | ✅             | ❌         | ❌          | Executes specific coding tasks  |
| QA      | ❌           | ✅ (fixes)     | ✅         | ❌          | Tests, validates, audits        |

---

## Phase 2: Core Implementation Requirements

### `factory/llm_manager.py` (Cost Control & Observability)

- `FailoverLLMManager` class
- **Token Tracing:** Native hooks for **Langfuse** / OpenTelemetry to monitor token usage and trace agent-to-tool routing.
- **Failover Target:** Prioritise **Google Gemini 2.5 Flash** (via Google AI Studio) as the default free tier engine before shifting to paid models (OpenAI, Anthropic).
- Pipeline config from environment variables
- Rate limit detection + auto-failover
- Daily budget tracking (USD limit)
- Provider abstraction: Gemini, OpenAI, Anthropic

### `factory/base_agent.py`

- `AgentFactory` class: `create(config) -> agent`
- `AgentConfig` dataclass (name, rank, role, tools, model, instructions)
- `RunnableAgent` class: wraps LangChain agent executor
- State management: `add_context()`, `clear_context()`

### `factory/base_tools.py`

- `@tool` decorator with name, description, category
- Tool registry: `register()`, `get()`, `list()`
- Args schema auto-generation from type hints
- Tool metadata: cost estimate, safety level

### `factory/mcp_integration.py`

- `MCPClientManager` class
- Auto-discover MCP servers from `mcp.json`
- Support for marketplace MCP servers
- Support for custom MCP servers
- Convert MCP tools to `@tool`-compatible functions

### `factory/verifier.py` (Context Optimization)

- `Verifier` class
- **Context Pruning:** The self-correction loop must compress error context. It is strictly forbidden from passing entire files back to the model during code failures; it must isolate and extract _only the failing lines_ and matching stack trace snippets.
- Pluggable verification stages: lint, test, security scan
- `VerificationReport` dataclass
- Self-correction loop with max iterations

### `factory/config.py`

- Pydantic `Settings` class
- `.env` file loading
- Type-safe configuration

### `agents/config_loader.py`

- YAML profile loader
- Template variable substitution
- Environment variable interpolation

### `app/approval_server.py` (State & Race Conditions)

- FastAPI endpoints: `/propose`, `/review`, `/status`, `/health`
- Discord webhook with interactive buttons
- Gmail notification via SMTP
- **State Persistence:** Replace volatile in-memory dictionary state tracking with a persistent transactional engine (**SQLite**). This prevents state loss on server reboots and introduces atomic state locks to block duplicate button click executions.
- **Database Engine:** Standardize on **SQLite** for zero-configuration, self-contained file database with atomic transactions and execution locks.

### `agentfactory/cli.py` (Developer Tooling)

- **Commands Pack:**
  - `agentfactory init`: Configures `.env` configurations, checks directory mappings, and validates setup.
  - `agentfactory run`: Multi-process bootloader to launch the FastAPI control plane and the background polling worker simultaneously.

### `tools/*.py`

- `git_tools.py`: branch creation, commit, push (never main)
- `web_tools.py`: web search, web fetch
- `file_tools.py`: read, write, analyze files
- `notify_tools.py`: Discord, Gmail, webhook

---

## Phase 3: Test Plan (Target: 25+ tests)

| Test File                 | Test Cases                                                       | Expected |
| ------------------------- | ---------------------------------------------------------------- | -------- |
| `test_llm_manager.py`     | Default pipeline, custom pipeline, failover, budget, reset       | 6        |
| `test_base_agent.py`      | Config creation, system prompt, agent run                        | 4        |
| `test_base_tools.py`      | Registration, retrieval, schema generation, categories           | 6        |
| `test_mcp_integration.py` | Client init, tool discovery, conversion                          | 5        |
| `test_verifier.py`        | Report creation, check pass/fail, self-correction, serialization | 5        |
| `test_config.py`          | Env loading, defaults, validation                                | 3        |
| `test_config_loader.py`   | YAML loading, template rendering                                 | 3        |
| `test_worker.py`          | Polling, execution, multi-repo sync                              | 3        |
| **Total**                 |                                                                  | **35**   |

---

## Phase 4: Packaging

- `.env.example` with all variables documented
- `LICENSE` (MIT)
- `README.md` with quick-start guide
- `docs/` with architecture and usage guides
- `requirements.txt` + `requirements-dev.txt`
- `pytest.ini` config
- `pyproject.toml` with entry point

---

## Phase 5: Personal Team Repo

A **separate repository** that:

- Depends on `agentfactory` as a package (or git submodule)
- Contains your specific configs: `agents/my_engineer_crew.yaml`
- Sets your repo paths: `BACKEND_PATH`, `FRONTEND_PATH`, `ADMIN_PATH`
- Custom tools for your specific needs
- `.env` with your API keys and webhooks
- Can be open-sourced as an example use case

---

## Status

- ✅ Phase 1: Planning complete
- ⬜ Phase 2: Implementation
- ⬜ Phase 3: Tests
- ⬜ Phase 4: Packaging
- ⬜ Phase 5: Personal team repo

---

## Questions for You

1. Should I use this plan, or do you want to adjust any of the architecture decisions?
2. For MCP integration — should it auto-discover from the user's `~/.mcp.json` or `mcp.json` in the project?
3. Any specific tech stack preferences beyond FastAPI + React? (database, monitoring tools, etc.)
4. Should the template include a CLI (`agentfactory init`, `agentfactory run`, etc.)?

---

_Waiting for your approval to proceed to Phase 2: Implementation_

## 3. Package Distribution & Delivery Model

- **SDK Wrapper:** Standardize on an **NPM Registry Node.js CLI wrapper** (`npx agentfactory`).
- **Automated Bootstrapping:** Node.js must handle environmental discovery, automatically verify local Python installations, provision an isolated virtual environment (`.venv`), install the python-core runtime, and manage background FastAPI/worker process lifecycles via a unified JS command system.

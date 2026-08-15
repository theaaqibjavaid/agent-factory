# Architecture

AgentFactory is a universal template for building AI agent systems. It ships with a reference implementation — a multi-tier engineering team — but the core framework can be used to create any type of agent.

## Core Design Principles

1. **LLM Failover**: Gemini (free) → OpenAI → Anthropic (paid), with USD budget control and Langfuse tracing
2. **Ranked Hierarchy**: Manager → Senior → Junior → QA agents with delegation control
3. **Pluggable Tools**: `@tool` decorator pattern with `SafetyLevel` classification
4. **Human-in-the-Loop**: FastAPI approval server with SQLite state persistence
5. **Multi-Repo Aware**: Configurable repository paths for backend/frontend/admin-panel
6. **Never Touches Main**: All changes via isolated branches + approval gates

## Component Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    User / CLI                           │
│  agentfactory init | run | create-agent | list-tools   │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                   AgentFactory                           │
│  (base_agent.py) — Creates agents from YAML configs    │
│  - AgentFactory: main factory class                     │
│  - RunnableAgent: agent instance with LLM + tools      │
│  - AgentConfig: pydantic config model                   │
└──────┬──────────────────────────┬───────────────────────┘
       │                          │
       │                          │
┌──────▼──────────────┐  ┌──────▼──────────────┐
│   FailoverLLMManager │  │   ToolRegistry       │
│  (llm_manager.py)    │  │  (base_tools.py)     │
│                      │  │                      │
│ - Gemini → OpenAI →  │  │ - @tool decorator    │
│   Anthropic pipeline │  │ - ToolDef dataclass  │
│ - Budget tracking    │  │ - SafetyLevel enum   │
│ - Langfuse tracing   │  │ - 28 built-in tools  │
│ - generate_text()    │  │ - MCP integration    │
└──────┬───────────────┘  └────────┬─────────────┘
       │                           │
┌──────▼──────────────┐  ┌────────▼─────────────┐
│     Verifier        │  │      MCP Client      │
│  (verifier.py)       │  │ (mcp_integration.py) │
│                     │  │                      │
│ - Context pruning   │  │ - load_mcp_config()  │
│ - Audit reports     │  │ - Server configs     │
│ - FailedCheck       │  │ - Tool discovery     │
└─────────────────────┘  └──────────────────────┘
       │                           │
       │                           │
┌──────▼──────────────┐  ┌────────▼─────────────┐
│  Approval Server    │  │  Background Worker    │
│ (app/approval_)     │  │ (agents/worker.py)    │
│    server.py        │  │                       │
│                     │  │ - Polls for tasks     │
│ - FastAPI           │  │ - Runs agents         │
│ - SQLite state      │  │ - Discord/Gmail       │
│ - Discord/Gmail     │  │   notifications       │
└─────────────────────┘  └──────────────────────┘
```

## Package Structure

```
agentfactory/
├── __init__.py              # Package exports
├── cli.py                   # CLI entry point (click)
├── config.py                # Pydantic Settings with .env loading
├── llm_manager.py           # FailoverLLMManager — LLM failover + budget
├── base_agent.py            # AgentFactory, RunnableAgent, AgentConfig
├── base_tools.py            # @tool decorator, ToolRegistry, ToolDef, SafetyLevel
├── verifier.py              # Verifier — post-execution audit + context pruning
├── mcp_integration.py       # MCPClient — MCP server integration
├── py.typed                 # PEP 561 type marker
│
├── tools/                   # Built-in tool implementations
│   ├── __init__.py          # Auto-registration + legacy aliases
│   ├── git_tools.py         # 8 git tools (branch, commit, PR, etc.)
│   ├── web_tools.py         # 3 web tools (search, fetch, scrape)
│   ├── file_tools.py        # 7 file tools (read, write, search, etc.)
│   └── notify_tools.py      # 3 notification tools (Discord, Gmail, webhook)
│
├── agents/                  # Agent config + worker
│   ├── config_loader.py     # YAML config parser + DEFAULT_REPO_PATHS
│   ├── worker.py            # Background polling worker
│   └── examples/
│       └── engineer_crew.yaml  # 3-tier team reference config
│
└── app/                     # FastAPI control plane
    └── approval_server.py   # FastAPI app — approval, state, notifications
```

Root-level files:
- `pyproject.toml` — Packaging, entry point, optional deps
- `requirements.txt` — Pinned dependencies
- `LICENSE` — MIT
- `README.md` — Project readme
- `CLAUDE.md` — Claude Code instructions
- `AGENTFACTORY-PLAN.md` — Development roadmap

## LLM Failover Pipeline

```
Request → Gemini 2.5 Flash (free tier)
              ↓ if rate-limited / fails
         OpenAI GPT-4o / GPT-4o-mini (paid)
              ↓ if rate-limited / fails
         Anthropic Claude (premium)
```

Budget control: `FailoverLLMManager` tracks daily spend, stops when `AGENT_DAILY_BUDGET_USD` is reached.

## Tool Safety Levels

| Level | Description | Example Tools |
|-------|-------------|---------------|
| `SAFE` | Read-only, no side effects | web_search, read_text_file |
| `MODIFIED` | Writes files, recoverable | write_text_file, git_commit_changes |
| `DESTRUCTIVE` | Could cause data loss | delete_file |

Tools default to `SAFE`. Destructive tools require explicit approval via the FastAPI server.

## Extending the Framework

AgentFactory is designed as a **dependency-first template**. Your personal team repo should:

1. `pip install agentfactory`
2. Import the core classes
3. Define your own agent YAML configs
4. Write custom tools with `@tool`
5. Use `AgentFactory` to spawn agents targeting your repos

See [Quick Start](quick-start.md) for usage examples.

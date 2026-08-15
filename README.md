# AgentFactory: Universal AI Agent Factory & Multi-Repo Engineering Team

## Overview

AgentFactory is a production-grade, open-source Python framework that acts as a universal template for creating any type of AI agent. It supports ranked agent hierarchies (Senior, Junior, QA, Manager), configurable LLM failover across free and paid tiers, a pluggable tool registry, and strict safety mechanisms.

The first reference implementation is an **Autonomous Hierarchical Software Engineering Team** that:
- Researches web trends and inspects multi-repository codebases (FastAPI backend, React frontend, Admin panel)
- Creates feature branches with mirrored names across all repos
- Writes code, runs tests, and triggers GitHub Actions CI/CD
- Never touches `main` — all changes require human approval via FastAPI/Discord/Gmail gates

## Architecture

```
agentfactory/
├── __init__.py              # Package exports (AgentFactory, RunnableAgent, cli)
├── cli.py                   # CLI entry point (init, run, create-agent, list-tools, status)
├── config.py                # Pydantic settings with .env loading
├── llm_manager.py           # FailoverLLMManager — LLM failover + budget control
├── base_agent.py            # AgentFactory, RunnableAgent, AgentConfig, AgentPersona
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
│   ├── engineering_crew.py  # Tiered engineering team orchestrator
│   └── examples/
│       └── engineer_crew.yaml  # 3-tier team reference config
│
└── app/                     # FastAPI control plane
    └── approval_server.py   # FastAPI app — approval, state, notifications

tests/                      # 56 tests (test_core.py, test_factory.py)
docs/                       # 14 documentation files
pyproject.toml              # Production packaging with entry point
requirements.txt            # Pinned dependencies
LICENSE                     # MIT
.env.example                # All environment variables documented
```

## Quick Start

```bash
# 1. Install as a package
pip install agentfactory

# 2. Set environment variables
export GEMINI_API_KEY="your-gemini-key"          # Free tier
export OPENAI_API_KEY="your-openai-key"          # Paid fallback
export ANTHROPIC_API_KEY="your-anthropic-key"    # Premium fallback
export DEV_NOTIF_WEBHOOK_URL="your-discord-webhook"
export GMAIL_USER="your-email@gmail.com"
export GMAIL_APP_PASSWORD="your-app-password"
export ADMIN_EMAIL="your-email@gmail.com"

export BACKEND_PATH="/absolute/path/to/fastapi-backend"
export FRONTEND_PATH="/absolute/path/to/react-frontend"
export ADMIN_PATH="/absolute/path/to/admin-panel"

# 3. Initialize (creates .env, mcp.json, example agent configs)
agentfactory init

# 4. Launch the FastAPI approval server + background worker
agentfactory run
```

## Usage

### Creating a New Agent Type

Any agent can be created by adding a YAML profile to `agents/`:

```yaml
# agents/my_custom_agent.yaml
agent_name: "DocumentProcessor"
rank: "Junior"
model_preference: ["gemini-2.5-flash", "gpt-4o-mini"]
system_instructions: |
  You are a document processing agent. Extract tables from PDFs and convert them to CSV.
tools:
  - parse_pdf
  - generate_csv
constitutional_boundaries:
  max_budget_usd_per_day: 2.00
```

### Creating a New Tool

Tools are registered via decorators in `base_tools.py`:

```python
@tool("process_document")
def process_document(file_path: str) -> str:
    """Process a document and extract structured data."""
    # Your tool logic here
    return result
```

## Constitutional Rules

1. **Branch Isolation**: All changes are pushed to `feature/*` branches. `main`/`master` are never touched.
2. **Approval Gate**: No code mutations execute until `approval_granted == True` in the FastAPI server.
3. **Budget Control**: Free tiers are exhausted first; paid tiers used only as fallback. Hard stop when budget exceeded.
4. **Verification Loop**: Every code change passes local tests (pytest, npm test) before being marked ready.

## License

MIT

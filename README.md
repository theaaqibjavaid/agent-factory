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
AgentFactory
├── factory/                        # Core universal template
│   ├── __init__.py
│   ├── llm_manager.py             # Failover router (free→paid tiers, budget control)
│   ├── base_agent.py              # Agent factory: spawn any agent from YAML
│   ├── base_tools.py              # Pluggable tool registry (decorator pattern)
│   └── verifier.py                # Post-execution verification & audit
├── agents/                         # Agent configurations
│   ├── config_loader.py           # YAML config parser
│   ├── engineer_crew.yaml         # 3-tier engineering team profiles
│   └── worker.py                  # Background worker (polls FastAPI for approvals)
├── app/
│   └── approval_server.py         # FastAPI control + Discord/Gmail notifications
├── tests/
│   ├── test_llm_manager.py
│   ├── test_base_agent.py
│   ├── test_tools.py
│   └── test_verifier.py
├── requirements.txt
├── README.md
└── pyproject.toml
```

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

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

# 3. Launch the FastAPI approval server
uvicorn app.approval_server:app --reload --port 8000

# 4. Launch the background worker
python agents/worker.py
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

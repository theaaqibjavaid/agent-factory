# Quick Start

Run your first AI agent team in 5 minutes.

## 1. Initialize

```bash
agentfactory init --force
```

This creates:
- `.env` — API keys and configuration
- `mcp.json` — MCP server config
- `agents/examples/` — Example agent YAML configs

## 2. Configure

Edit `.env` and add your API keys. At minimum, set `GEMINI_API_KEY`:

```bash
GEMINI_API_KEY=your-gemini-key-here
OPENAI_API_KEY=your-openai-key-here
```

## 3. Start the System

> **New to the Studio platform?** Run the full product (API + dashboard in one
> process) with `agentfactory studio` and open http://localhost:8000. The
> commands below are the **legacy v1 SDK flow** (approval server + worker).

```bash
agentfactory run
```

This starts:
- **FastAPI approval server** at `http://localhost:8000` (API docs at `/docs`)
- **Background worker** that polls for approved agent tasks

Or run separately:

```bash
# Server only
uvicorn agentfactory.app.approval_server:app --port 8000 --reload

# Worker only (from your separate repo)
python -m agentfactory.agents.worker --watch
```

## 4. Use the CLI

```bash
# List all tools (28 built-in tools)
agentfactory list-tools

# Create a new agent config
agentfactory create-agent my_researcher --rank Senior

# Check server status
agentfactory status
```

## 5. Write Your First Agent (from YAML)

Create `agents/my_agent.yaml`:

```yaml
agent_name: "MyBot"
rank: "Senior"
model_preference: ["gemini-2.5-flash", "gpt-4o"]
responsibilities: "Research and summarize technical topics"
tools: ["web_search", "web_fetch", "list_directory_contents"]
system_instructions: "You are a helpful research assistant."
constitutional_boundaries:
  max_budget_usd_per_day: 2.00
allow_delegation: true
```

## 6. Using as a Dependency (Phase 5)

This template is designed to be used as a Python package dependency in your own agent projects:

```bash
pip install agentfactory-studio
```

```python
from agentfactory.core import AgentFactory
from agentfactory.config import LLMConfig
from agentfactory.base_tools import tool, ToolRegistry

# Import built-in tools
import agentfactory.tools

# Your custom tools
@tool("my_custom_tool", category="custom")
def my_custom_tool(data: str) -> str:
    """Process data."""
    return f"Processed: {data}"

# Create your agent
factory = AgentFactory()
agent = factory.create_agent("MyAgent", rank="Senior")
```

## Next Steps

- Read [Architecture](architecture.md) to understand the design
- Review [CLI Reference](cli-reference.md) for all commands
- See [Agent Configuration](agent-config.md) for YAML schema details
- Learn about [writing custom tools](tools.md)

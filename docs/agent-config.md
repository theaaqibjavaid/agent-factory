# Agent Configuration

Agent configs are YAML files that define agent behavior, tools, and LLM preferences.

## Basic Schema

```yaml
agent_name: "MyAgent"
rank: "Senior"          # Senior, Junior, QA, or Manager
model_preference: ["gemini-2.5-flash", "gpt-4o"]
responsibilities: "Description of what this agent does"
tools: ["web_search", "web_fetch"]
system_instructions: "Detailed system prompt for the agent"
constitutional_boundaries:
  max_budget_usd_per_day: 2.00
allow_delegation: true
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `agent_name` | string | Human-readable name |
| `rank` | string | Agent tier: `Manager`, `Senior`, `Junior`, or `QA` |
| `model_preference` | list | Ordered LLM models (free → paid) |
| `responsibilities` | string | What this agent is responsible for |
| `tools` | list | List of registered tool names |
| `system_instructions` | string | Full system prompt |
| `constitutional_boundaries` | object | Constraints (e.g., budget, never_touch_main) |
| `allow_delegation` | boolean | Can this agent delegate to other agents |

## Multi-Agent Team Config

```yaml
system_architecture: "Hierarchical_Supervisor_Worker"
max_worker_iterations: 2
failover_enabled: true

repo_paths:
  backend: ${BACKEND_PATH}
  frontend: ${FRONTEND_PATH}
  admin_panel: ${ADMIN_PATH}

agents:
  - name: "Senior_Lead_Architect"
    rank: "Senior"
    model_preference: ["gemini-2.5-flash", "gpt-4o"]
    responsibilities: "Research, analyze repos, produce blueprints"
    allow_delegation: true
    tools: ["web_search", "list_directory_contents"]

  - name: "Junior_Feature_Engineer"
    rank: "Junior"
    model_preference: ["gemini-2.5-flash", "gpt-4o-mini"]
    responsibilities: "Write code on isolated branches"
    allow_delegation: false
    tools: ["git_create_branch", "write_text_file", "git_commit_changes"]

  - name: "QA_Security_Auditor"
    rank: "QA"
    model_preference: ["gpt-4o-mini"]
    responsibilities: "Run tests and linters"
    allow_delegation: false
    tools: ["list_directory_contents"]
```

## Creating Configs

### From CLI

```bash
agentfactory create-agent my_researcher --rank Senior
```

### From Python

```python
import yaml

config = {
    "agent_name": "MyBot",
    "rank": "Senior",
    "model_preference": ["gemini-2.5-flash", "gpt-4o"],
    "tools": ["web_search", "web_fetch"],
    "system_instructions": "You are a helpful assistant.",
}

with open("agents/my_agent.yaml", "w") as f:
    yaml.dump(config, f)
```

## Loading Configs

```python
from agentfactory.agents.config_loader import load_agent_config

config = load_agent_config("agents/my_agent.yaml")
```

## Example Configs

See `agents/examples/engineer_crew.yaml` for the complete 3-tier engineering team reference config.

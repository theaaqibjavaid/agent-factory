# Persistent Memory Layer

AgentFactory includes a SQLite-backed persistent memory system that allows agents to
remember facts and conversation history across sessions.

## Overview

The memory system is implemented in [`agentfactory/memory.py`](memory.md) and provides:

- **Conversation history**: Rolling window of past interactions, persisted to SQLite
- **Key-value facts**: Arbitrary facts stored per-agent with isolation
- **Thread-safe access**: Uses `threading.Lock` and SQLite WAL mode for concurrent safety

## Configuration

Memory is configured via environment variables (see [Environment Variables](env-vars.md)):

| Variable | Description | Default |
|----------|-------------|---------|
| `MEMORY_DB_PATH` | Path to SQLite memory database | `~/.agentfactory/memory.db` |
| `MEMORY_AGENT_ID` | Default agent ID for memory isolation | `default` |

## Usage

### Programmatic API

```python
from agentfactory import PersistentMemory

# Create a memory instance
mem = PersistentMemory(agent_id="my-agent")

# Save a fact
mem.save_fact("user_name", "Alice")
mem.save_fact("preferred_style", "concise")

# Recall a fact
name = mem.load_fact("user_name")  # "Alice"

# List all facts (with optional prefix filter)
facts = mem.list_facts(prefix="user_")

# Delete a fact
mem.delete_fact("user_name")

# Save/Load conversation history
mem.save_history([
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi there!"},
])
history = mem.load_history(limit=50)

mem.close()
```

### Via Agent

Agents automatically use persistent memory when a `PersistentMemory` instance is
provided or `agent_id` is set:

```python
from agentfactory import AgentFactory

factory = AgentFactory()
agent = factory.create_agent("Senior", repo_name="my-project")

# The agent automatically saves conversation history to memory
await agent.run("Implement user authentication")
# History is persisted — next run picks up from where you left off
```

### Via Tools

Agents can interact with memory using built-in `@tool`-decorated functions:

| Tool | Category | Description |
|------|----------|-------------|
| `save_memory` | memory | Save a key-value fact to persistent memory |
| `recall_memory` | memory | Recall a fact by key |
| `list_memory` | memory | List all stored facts (with optional prefix filter) |
| `forget_memory` | memory | Delete a fact (DESTRUCTIVE — requires approval) |

```python
# Agent can call these tools during execution:
# save_memory("last_task", "implement auth")
# recall_memory("last_task")  # → "implement auth"
# list_memory()  # Lists all facts
# forget_memory("stale_fact")  # Deletes the fact
```

## Architecture

```
┌─────────────────────────────────────────────┐
│           PersistentMemory                  │
│  (agentfactory/memory.py)                   │
│                                             │
│  SQLite (file-based, WAL mode)              │
│  ├── facts table                            │
│  │   - agent_id (partition)                 │
│  │   - key, value                           │
│  │   - created_at, expires_at               │
│  └── history table                          │
│      - agent_id (partition)                 │
│      - role, content                        │
│      - created_at                           │
└─────────────────────────────────────────────┘
```

## Safety Levels

| Tool | Safety Level | Requires Approval |
|------|-------------|-------------------|
| `save_memory` | `SAFE` | No |
| `recall_memory` | `SAFE` | No |
| `list_memory` | `SAFE` | No |
| `forget_memory` | `DESTRUCTIVE` | Yes |

# Architecture

AgentFactory is a universal template for building AI agent systems. It ships with a reference implementation — a multi-tier engineering team — but the core framework can be used to create any type of agent (Excel experts, email assistants, researchers, code agents, etc.).

## Core Design Principles

1. **LLM Failover**: Gemini (free) → OpenAI → Anthropic (paid), with USD budget control and Langfuse tracing
2. **Ranked Hierarchy**: Manager → Senior → Junior → QA agents with delegation control
3. **Pluggable Tools**: `@tool` decorator pattern with `SafetyLevel` classification
4. **Human-in-the-Loop**: FastAPI approval server with SQLite state persistence and JWT auth
5. **Multi-Repo Aware**: Configurable repository paths for backend/frontend/admin-panel
6. **Never Touches Main**: All changes via isolated branches + approval gates
7. **Persistent Memory**: SQLite-backed fact storage and conversation history across sessions
8. **Skill Marketplace**: Dynamic skill loading from packages or directories
9. **Feedback Learning**: `learn_from_correction()` for agents to improve from corrections

## Package Structure

```
agentfactory/
├── __init__.py              # Package exports (AgentFactory, RunnableAgent, Skill, Memory, etc.)
├── cli.py                   # CLI entry point (click)
├── config.py                # Pydantic Settings with .env loading
├── llm_manager.py           # FailoverLLMManager — LLM failover + budget + streaming + tool calling
├── base_agent.py            # AgentFactory, RunnableAgent, AgentConfig, AgentPersona
├── base_tools.py            # @tool decorator, ToolRegistry, ToolDef, SafetyLevel
├── verifier.py              # Verifier — post-execution audit + context pruning
├── mcp_integration.py       # MCPClient — async MCP server integration
├── memory.py                # PersistentMemory — SQLite-backed conversation + facts
├── skill.py                 # Skill, SkillRegistry — skill marketplace
├── py.typed                 # PEP 561 type marker
│
├── tools/                   # Built-in tool implementations
│   ├── __init__.py
│   ├── git_tools.py
│   ├── web_tools.py
│   ├── file_tools.py
│   ├── notify_tools.py
│   └── memory_tools.py
│
├── agents/
│   ├── config_loader.py
│   ├── worker.py
│   └── examples/engineer_crew.yaml
│
└── app/
    └── approval_server.py   # FastAPI app — approval, state, JWT auth, notifications
```

## LLM Failover Pipeline

Request goes through: Gemini 2.5 Flash (free tier) → OpenAI GPT-4o (paid) → Anthropic Claude (premium).
Budget tracking via `FailoverLLMManager` with daily USD limit.

Streaming and native tool calling are supported via `generate_streaming()` and `generate_with_tools()`.

## Tool Safety Levels

| Level | Description | Example Tools |
|-------|-------------|---------------|
| `SAFE` | Read-only, no side effects | web_search, recall_memory |
| `MODIFIED` | Writes files, recoverable | write_text_file, save_memory |
| `DESTRUCTIVE` | Could cause data loss | delete_file, forget_memory |

## Memory Architecture

`PersistentMemory` in `agentfactory/memory.py` provides SQLite-backed:
- **Fact storage**: key-value pairs partitioned by agent_id
- **History**: rolling conversation window persisted to disk
- **Thread-safe**: uses threading.Lock + SQLite WAL mode

See [Persistent Memory](memory.md) for details.

## Skill Marketplace

`SkillRegistry` in `agentfactory/skill.py` provides:
- Programmatic skill registration
- Package loading (`load_skill_package`)
- Directory loading (`load_skills_from_directory`)
- Dependency resolution

See [Skills](skills.md) for details.

## Feedback Learning

`RunnableAgent.learn_from_correction()` allows agents to learn from human corrections
by re-running tasks with correction context and persisting to memory.

## Extending the Framework

1. `pip install agentfactory-studio`
2. Write custom tools with `@tool`
3. Define agent configs via `AgentPersona`
4. Use `AgentFactory` to spawn agents targeting your repos

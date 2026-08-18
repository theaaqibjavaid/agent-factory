# Architecture

> **Status: Current / legacy implementation reference.**
>
> This document describes the existing AgentFactory implementation. It is not the target NeuraHive v2 architecture. For future architecture work, use `NEURAHIVE_V2_ROADMAP.md` and `NEURAHIVE_ARCHITECTURE_CONTRACT.md`.

AgentFactory is the current universal template for building AI agent systems. It ships with a reference implementation — a multi-tier engineering team — but the current framework can be used to create different types of agents (Excel agents, software engineers, researchers, etc.).

## Current implementation principles

1. **LLM Failover**: Gemini → OpenAI → Anthropic, with USD budget control and tracing
2. **Ranked Hierarchy**: Manager → Senior → Junior → QA agents with delegation control
3. **Pluggable Tools**: `@tool` decorator pattern with `SafetyLevel` classification
4. **Human-in-the-Loop**: FastAPI approval server with SQLite state persistence and JWT auth
5. **Multi-Repo Aware**: Configurable repository paths for backend/frontend/admin-panel
6. **Never Touches Main**: All changes via isolated branches + approval gates
7. **Persistent Memory**: SQLite-backed fact storage and conversation history
8. **Skill Marketplace**: Dynamic skill loading from packages or directories
9. **Feedback Learning**: `learn_from_correction()` for agents to improve from corrections

## Current package structure

```text
agentfactory/                 # LEGACY / CURRENT package
├── __init__.py
├── cli.py
├── config.py
├── llm_manager.py
├── base_agent.py
├── base_tools.py
├── verifier.py
├── mcp_integration.py
├── memory.py
├── skill.py
├── tools/
├── agents/
└── app/                      # PLATFORM / control-plane code
    └── approval_server.py

neurahive/                    # v2 core boundary introduced in Phase 0
└── __init__.py               # Contracts are introduced incrementally in Phase 1+
```

The existing `agentfactory` package intentionally remains intact during migration. Its platform-aware runtime and application modules are not considered part of the final v2 core boundary.

## v2 target architecture

NeuraHive v2 reverses the current coupling:

```text
Project / Platform / Studio
          |
          v
     Public NeuraHive API
          |
          v
      Core Runtime
          |
          v
     Providers / Executors
```

The core must not depend on platform DB state, Studio, Mausam, or another consuming application. Platform code resolves persisted configuration and injects providers into the core.

## Migration

The `agentfactory` namespace remains the compatibility surface while the canonical `neurahive` namespace is built. See `migration-v1-v2-package-compatibility.md` for the package and API transition strategy.

## Current LLM failover

The current implementation supports a configured failover chain with budget tracking, streaming, and native tool calling.

## Current tool safety levels

| Level | Description | Example Tools |
|-------|-------------|---------------|
| `SAFE` | Read-only, no side effects | web_search, recall_memory |
| `MODIFIED` | Writes files, recoverable | write_text_file, save_memory |
| `DESTRUCTIVE` | Could cause data loss | delete_file, forget_memory |

## Current memory

`PersistentMemory` provides SQLite-backed fact storage and conversation history. In v2, this implementation will sit behind the `MemoryProvider` abstraction rather than define the public architecture.

## Current skills

`SkillRegistry` provides programmatic and package/directory skill loading. In v2, skills and plugin/provider contracts become part of the public core API.

## Current extension path

Existing consumers continue using `agentfactory` during the migration. New v2 consumers should use the documented `neurahive` public API once the relevant Phase 1+ contracts are implemented.

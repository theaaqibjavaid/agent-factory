# NeuraHive v2 — Public API Inventory

> Phase 0 baseline. This document defines what may become a supported consumer API. Importability alone does not make a symbol public.

## 1. Public API policy

A symbol is public only when all of the following are true:

1. It is intentionally exported from a documented public module.
2. Its behavior is described in documentation.
3. It has contract/regression coverage.
4. Its compatibility level is stated.
5. Breaking changes have a migration path.

Internal modules may change without consumer compatibility guarantees.

## 2. Current compatibility surface

The repository currently exports these legacy symbols from `agentfactory`:

| Symbol | Current source | v2 disposition |
|---|---|---|
| `AgentFactory` | `base_agent.py` | Compatibility facade; replace with v2 composition API |
| `RunnableAgent` | `base_agent.py` | Compatibility facade; evolve toward `Agent` + runtime |
| `Skill` | `skill.py` | Retain as public contract |
| `SkillRegistry` | `skill.py` | Retain; evolve toward provider/plugin registry |
| `PersistentMemory` | `memory.py` | Keep as implementation; public abstraction becomes `MemoryProvider` |
| `MCPServerConfig` | `mcp_integration.py` | Retain as MCP configuration contract |
| `MCPClient` | `mcp_integration.py` | Retain as adapter; execution details remain internal |
| `cli` | `cli.py` | Compatibility surface; future canonical CLI is `neurahive` |

The current package still imports platform-aware modules and is therefore **not yet the final v2 core boundary**. Phase 0 records this intentionally rather than pretending the separation is already complete.

## 3. Target v2 public surface

The target stable surface is organized by capability:

```text
neurahive
├── Agent
├── AgentConfig
├── AgentContext
├── AgentResult
├── AgentRuntime
│
├── Tool
├── ToolRegistry
├── ToolResult
│
├── Model
├── ModelProvider
├── ModelRouter
│
├── MemoryProvider
│
├── Skill
├── Plugin
│
├── Workflow
├── Task
├── WorkflowRunner
│
├── Policy
├── PolicyDecision
│
├── Verifier
├── VerificationResult
│
├── Event
├── EventSink
│
└── core exceptions / validation types
```

These names are architectural targets, not a promise that they already exist in the current implementation.

## 4. Public versus internal examples

### Public

```python
from neurahive import Agent, ToolRegistry, Workflow
```

### Internal

```python
from neurahive.runtime._execution import _ExecutionState
```

Internal modules may be reorganized without preserving import compatibility.

## 5. Compatibility levels

| Level | Meaning |
|---|---|
| Stable | Supported across a minor release; breaking changes require migration notes |
| Experimental | Public but may change after explicit warning |
| Compatibility | Legacy API retained during migration; not the target design |
| Internal | No consumer compatibility guarantee |

## 6. Consumer acceptance test

An unrelated project must eventually be able to do:

```bash
pip install neurahive
```

and build its own agents, tools, skills, memory, policies, models, and workflows using only the Stable/Experimental public surface, with no NeuraHive source modification.

# NeuraHive v1 → v2 Package Compatibility Strategy

## Status

Phase 0 architecture contract.

## Objective

Move the reusable SDK from the legacy `agentfactory` package toward the canonical `neurahive` package without breaking existing consumers during the transition.

## Package roles

- `agentfactory`: legacy compatibility namespace during migration.
- `neurahive`: canonical v2 namespace.
- Studio/platform code: optional consumer of `neurahive`; it must not become a dependency of the core SDK.

## Migration rules

1. Do not rename the existing package in place during the early v2 phases.
2. Introduce the v2 core under `neurahive` with explicit public exports.
3. Keep legacy `agentfactory` symbols working through compatibility facades/adapters where feasible.
4. Do not expose platform internals as part of the v2 public API.
5. New documentation and examples should prefer `neurahive` once the package exists.
6. Compatibility shims must not introduce a reverse dependency from v2 core into Studio/platform state.

## Compatibility classification

| Legacy | v2 direction | Classification |
|---|---|---|
| `AgentFactory` | `Agent` + `AgentRuntime` composition | Compatibility |
| `RunnableAgent` | `Agent` + runtime | Compatibility |
| `Skill` | `Skill` | Stable/retained |
| `SkillRegistry` | `Skill`/provider registry | Compatibility → retained contract |
| `PersistentMemory` | `MemoryProvider` + SQLite provider | Implementation/compatibility |
| `MCPServerConfig` | MCP configuration/provider contracts | Compatibility |
| `MCPClient` | MCP adapter/provider | Compatibility |
| `agentfactory.cli` | `neurahive` CLI | Compatibility |

## Import policy

Canonical v2 consumers should eventually be able to write:

```python
from neurahive import Agent, AgentRuntime, ToolRegistry, Workflow
```

Legacy consumers may continue to write:

```python
from agentfactory import AgentFactory, RunnableAgent
```

The two surfaces must be tested independently.

## Distribution naming

The target distribution/import naming is `neurahive`. The existing distribution remains unchanged until the v2 packaging strategy can provide a safe transition. The repository must not perform a destructive package rename merely to satisfy naming goals.

## Deprecation policy

A legacy symbol may be deprecated only after:

- a v2 replacement exists;
- the replacement is documented;
- compatibility coverage exists;
- migration instructions exist;
- the deprecation is announced in release notes.

No legacy API is removed solely because the v2 architecture exists.

## Exit condition

The migration is complete when an unrelated project can install the canonical NeuraHive distribution, use only public v2 APIs, and operate without importing `agentfactory` or any platform/Studio internals.

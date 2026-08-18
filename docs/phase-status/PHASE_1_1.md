# Phase 1.1 — Legacy Compatibility + External Consumer Contract

**Status:** In progress
**Branch:** `feature/phase-1-sdk-core-separation`
**Base:** `feature/phase-0-architecture-contract`
**Main/dev:** untouched

## Why this sub-phase exists

During Phase 1 implementation, the architecture was refined: the legacy `RunnableAgent` should **not** be copied into the NeuraHive core. It combines model failover, memory, MCP, verification, tool execution, history, and retry policy in one platform-era object.

Instead, NeuraHive will expose small provider-neutral contracts and an explicit compatibility adapter. This preserves existing AgentFactory consumers while moving the canonical execution model toward injected dependencies.

## Current work

1. Define the legacy → NeuraHive compatibility mapping.
2. Add an external-consumer example that uses only public `neurahive` APIs.
3. Add compatibility tests that prove the legacy namespace remains available while the v2 namespace is independent.
4. Keep the adapter in the legacy compatibility boundary; do not import legacy platform modules from NeuraHive core.
5. Update the master roadmap and architecture documentation whenever an implementation decision changes the target architecture.

## Compatibility mapping

| Legacy concern | NeuraHive v2 target |
|---|---|
| `AgentFactory.create_agent()` | Consumer-owned `Agent` construction/factory |
| `RunnableAgent.run()` | `Agent.run()` / `AgentRuntime.run()` |
| LLM manager/failover | `ModelProvider` + future provider/retry adapters |
| `PersistentMemory` | `MemoryProvider` implementation |
| `SkillRegistry` | project-owned tool/skill registration |
| MCP client | `MCPProvider` adapter |
| verification | `Verifier` contract |
| tool execution | `ToolExecutor` |
| history/statistics | future execution state/event contracts |

## Architecture rule

NeuraHive core must never import `agentfactory.app`, platform database modules, Studio modules, or project-specific registries merely to make a legacy API work.

Compatibility may depend on NeuraHive, but NeuraHive must not depend on compatibility.

## External consumer acceptance test

An unrelated project must be able to:

- import `neurahive`;
- construct an `Agent` with injected dependencies;
- execute it through `InProcessRuntime`;
- avoid importing `agentfactory`, FastAPI, SQLAlchemy, Studio, or platform modules.

## Exit criteria

Phase 1.1 is complete when the compatibility mapping is documented and tested, an external consumer example is executable, and the compatibility surface has no reverse dependency into NeuraHive core.

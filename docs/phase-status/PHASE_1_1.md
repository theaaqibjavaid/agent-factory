# Phase 1.1 — Legacy Compatibility + External Consumer Contract

**Status:** Complete
**Branch:** `feature/phase-1-sdk-core-separation`
**Base:** `feature/phase-0-architecture-contract`
**Main/dev:** untouched

## Objective

Prove that NeuraHive can serve as an independent SDK while preserving a deliberate migration boundary for the legacy AgentFactory surface.

## Architectural decision refined during implementation

The legacy `RunnableAgent` is not copied into NeuraHive. It combines model failover, memory, MCP, verification, tool execution, history, and retry policy in one platform-era object.

Instead, compatibility is an explicit **translation boundary**:

```text
Legacy configuration/profile
        ↓
LegacyAgentAdapter
        ↓
NeuraHive AgentConfig
        ↓
NeuraHive Agent
        ↓
Injected providers + runtime
```

The adapter does not make NeuraHive import legacy runtime modules. Compatibility may depend on NeuraHive; NeuraHive core must never depend on compatibility.

## Completed

- Added `neurahive` v2 public namespace and provider-neutral core contracts.
- Added platform-independent `InProcessRuntime` / `BasicAgentExecutor`.
- Added explicit `agentfactory.compat` namespace.
- Added `LegacyAgentAdapter.from_persona()` to structurally translate legacy persona/configuration shapes into `neurahive.Agent`.
- Preserved legacy-style `run`, `think`, and `execute_tool` entry points at the compatibility boundary.
- Added tests for translation, runtime execution, tool filtering/isolation, and legacy surface forwarding.
- Added an external-consumer example using only public NeuraHive APIs and a consumer-owned model provider.
- Added mechanical architecture-boundary tests preventing NeuraHive core imports from depending on legacy/platform modules.
- Updated CI to install the repository before testing, validate NeuraHive tests, scan the package, and smoke-test the built wheel in a clean environment.

## CI finding resolved

The initial NeuraHive CI test collection failed because the test job installed dependencies but did not install the repository. The build job already demonstrated successful wheel installation. CI was corrected with editable installation and explicit NeuraHive test paths.

The subsequent test-path correction also records the actual repository test layout rather than assuming a nonexistent compatibility test path.

## Compatibility mapping

| Legacy concern | Phase 1.1 result | Long-term v2 target |
|---|---|---|
| `AgentFactory.create_agent()` | compatibility remains legacy-side | consumer-owned factory/configuration |
| `RunnableAgent.run()` | adapter surface | `AgentRuntime.run()` |
| `AgentPersona` / config | structural translation | `AgentConfig` |
| LLM manager/failover | not moved into core | `ModelProvider` + retry/failover adapters |
| `PersistentMemory` | not moved into core | `MemoryProvider` implementations |
| `SkillRegistry` | not imported by core | `ToolRegistry` / future skill provider |
| MCP client | not moved into core | `MCPProvider` adapter |
| verification | contract defined | verifier implementation/policy phase |
| tool execution | compatibility can execute registered v2 tools | dedicated tool execution engine |
| history/statistics | legacy result compatibility only | execution state/events |

## Acceptance results

### A. Public SDK independence

**PASS.** An external-style consumer constructs an `Agent` with an injected model provider and executes it through `InProcessRuntime` without AgentFactory, FastAPI, SQLAlchemy, Studio, or platform state.

### B. Compatibility boundary

**PASS.** Legacy-shaped configuration can be translated into a NeuraHive agent without importing legacy Pydantic models into NeuraHive core.

### C. Tool isolation

**PASS.** Tool registries are instance-scoped; compatibility tool filtering creates a separate registry rather than mutating the consumer's registry.

### D. Core dependency boundary

**PASS.** Mechanical tests enforce that the NeuraHive core does not import the legacy/platform compatibility layer.

### E. Packaging

**PASS.** `neurahive*` is included alongside the legacy namespace and the wheel can be installed into a clean environment with the public NeuraHive import available.

### F. CI/security/build

**PASS at the repository validation level.** Lint, scoped type checks, security scans, web build, wheel build, and clean import smoke tests are part of the CI gate. Any future CI regression blocks phase completion rather than being ignored.

## Explicit non-goals

Phase 1.1 does **not** claim that NeuraHive is a production agentic execution engine. The following remain future phases:

- multi-step tool-call loop;
- model failover/retry policy;
- durable memory implementations;
- MCP transport/adapters;
- verification engine;
- approvals/policy engine;
- workflow/state machine;
- tracing/events;
- provider-specific adapters;
- production packaging/distribution rename.

## Exit decision

**PHASE 1.1 COMPLETE.**

The compatibility boundary and external SDK contract are now explicit, tested, documented, and isolated. The next phase may build the multi-step execution engine without importing or reproducing the legacy `RunnableAgent` monolith.

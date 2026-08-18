# NeuraHive v2 — Master Roadmap

> **Status:** Active implementation roadmap
> **Planning baseline:** `feature/neurahive-v2-roadmap-docs`
> **Current implementation:** `feature/phase-1-sdk-core-separation`
> **Main/dev:** untouched

## Product Vision

**NeuraHive is the runtime and SDK for building programmable intelligent systems.** A consuming project installs NeuraHive and defines agents, tools, skills, memory providers, policies, models, and workflows outside the core. New project-specific agents/workflows must never require modifying NeuraHive source.

> **Install NeuraHive. Compose intelligent systems outside the core. Upgrade the engine independently.**

Mausam is one reference consumer; unrelated client projects must be equally possible.

## Non-Negotiable Architecture

1. Core is project-agnostic.
2. Public contracts precede implementations.
3. SDK first: Studio/platform consumes SDK; SDK does not depend on Studio.
4. Configuration over modification.
5. Dependency injection over platform lookups.
6. Providers are replaceable.
7. Native structured tool calling is canonical.
8. Trusted and untrusted execution have different security boundaries.
9. Workflows are first-class.
10. Backward compatibility requires an explicit migration path where feasible.
11. **Documentation is part of implementation:** any architecture/roadmap change discovered during implementation must be recorded in the roadmap, phase-status, ADR, or migration documentation before the phase is complete.

## Target Architecture

```text
Consumers: Mausam / Studio / CLI / Client Project
                    |
                    v
            NeuraHive public API
                    |
       +------------+------------+
       |            |            |
     Agents     Workflows      Models
       |            |            |
       +------------+------------+
                    |
                 Runtime
                    |
       +------------+------------+
       |            |            |
     Tools       Memory        Skills
       |            |            |
       +------------+------------+
                    |
       Policies / MCP / Verification
                    |
                 Execution
```

Dependency rule: **consumer/platform resolves dependencies → NeuraHive receives dependencies → runtime executes.** Core never discovers project/platform state itself.

## Phase Plan

### Phase 0 — Architecture Contract
**Priority:** P0 | **Status:** branch review/in progress

Freeze public boundaries, dependency direction, compatibility policy, package conventions, ADR structure and acceptance gates.

### Phase 1 — SDK/Core Separation
**Priority:** P0 | **Status:** active

Extract provider-neutral contracts and a platform-independent execution path without copying the legacy monolithic runtime.

Implemented: `neurahive` namespace; injected Agent contracts; Model/Memory/Tool contracts; verification/ToolExecutor/MCP contracts; `BasicAgentExecutor`; `InProcessRuntime`; core/platform import boundary; independent tests; external consumer example; v1→v2 compatibility strategy.

### Phase 1.1 — Compatibility + External Consumer Contract
**Priority:** P0 | **Status:** **complete**

**Architecture change discovered during implementation:** the legacy `RunnableAgent` is a platform-era monolith combining model failover, memory, MCP, verification, tool execution, history and retry behavior. It is **not** copied into NeuraHive core. Compatibility is an explicit translation boundary.

Completed:

- legacy-shaped persona/configuration → `NeuraHive AgentConfig` translation;
- explicit `agentfactory.compat` namespace;
- compatibility `run`, `think`, and `execute_tool` surfaces;
- external consumer example using only public `neurahive` APIs;
- compatibility and isolation tests;
- CI/build validation for the new namespace;
- documentation, roadmap, and migration records synchronized with the implementation decision.

Exit result: **PASS.** Compatibility mapping is documented/tested; external consumer execution is demonstrated; no reverse dependency from NeuraHive core into compatibility/platform code.

### Phase 2 — Agent API v2
**Priority:** P0 | **Status:** planned

Configuration-first agents with validated identity, instructions, model requirements, fallback, tools, skills, memory, permissions, budgets, context, delegation and verification.

### Phase 3 — Tool System v2
**Priority:** P0 | **Status:** planned

Typed, schema-driven, policy-aware tools with injected registries, built-in/project/decorator/MCP/plugin sources.

### Phase 4 — Runtime and Native Tool Calling
**Priority:** P0 | **Status:** planned

Canonical loop: `Model → structured tool call → schema validation → policy → approval → execute → result → Model`, plus retries, cancellation and lifecycle semantics.

### Phase 5 — Model Layer and Routing
**Priority:** P1 | **Status:** planned

Model catalog, capability requirements, provider routing, pricing/availability metadata and failover.

### Phase 6 — Memory Provider Architecture
**Priority:** P1 | **Status:** planned

Replaceable in-memory, SQLite, PostgreSQL, Redis, vector and custom memory implementations.

### Phase 7 — Skills and Plugin Contracts
**Priority:** P1 | **Status:** planned

Composable skills/plugins with version, compatibility and permission checks.

### Phase 8 — Policy and Permissions Engine
**Priority:** P1 | **Status:** planned

Central authorization for privileged tools, filesystem/network/shell, delegation, secrets, approvals and budgets.

### Phase 9 — Workflow Engine
**Priority:** P1 | **Status:** planned

Sequential, parallel, conditional, retry, loop/replanning, approval, fan-out/fan-in and cancellation workflows.

### Phase 10 — Multi-Agent Orchestration
**Priority:** P1 | **Status:** planned

Supervisor/worker, hierarchical, peer, reviewer, delegation and specialist patterns with explicit context/budget/depth controls.

### Phase 11 — Durable Task State and Events
**Priority:** P1 | **Status:** planned

Execution state machine, run/task identity, durable restart semantics and event streams consumable by Studio/logging/billing without coupling core.

### Phase 12 — Worker/Execution Architecture
**Priority:** P2 | **Status:** planned

Queue/worker boundary for long-running and concurrent execution; infrastructure remains replaceable.

### Phase 13 — Strong Sandbox Boundary
**Priority:** P2 | **Status:** planned

Isolated execution for untrusted tools with resource, filesystem, network and secret controls.

### Phase 14 — CLI and Project Scaffolding
**Priority:** P1 | **Status:** planned

`neurahive create-project`, agent/workflow scaffolding, run and diagnostics commands.

### Phase 15 — Studio as SDK Consumer
**Priority:** P1 | **Status:** planned

Reverse dependency direction so Studio/API/platform consumes the same public SDK contracts as external projects.

### Phase 16 — Contract Testing and Compatibility
**Priority:** P1 | **Status:** planned

Shared contract suites for providers, workflows, plugins, policies, event sinks and sandbox executors.

### Phase 17 — Examples and Reference Implementations
**Priority:** P1 | **Status:** planned

Unrelated coding, research, support and Mausam-style examples plus multi-agent workflows.

### Phase 18 — Packaging and Release Engineering
**Priority:** P1 | **Status:** planned

Canonical distribution/import/CLI name `neurahive`, optional provider extras, clean installs, release/version/migration policy.

## Repository Mapping

| Current area | v2 direction |
|---|---|
| `base_agent.py` | compatibility surface → Agent/runtime contracts |
| `base_tools.py` | Tool contracts and schema system |
| `llm_manager.py` | Model/Provider/Router/Catalog adapters |
| `memory.py` | MemoryProvider adapters |
| `skill.py` | Skill/Plugin contracts |
| `mcp_integration.py` | MCP adapter behind public interface |
| `verifier.py` | Verification contracts |
| `runtime.py` | platform-independent runtime |
| `app/*` | platform-only |
| `web/*` | Studio-only |
| global registries | compatibility only; injected registries canonical |

## Implementation Tracking Rule

Every implementation branch keeps its phase-status document current. When implementation reveals a better boundary, sequencing change, new dependency, or new acceptance requirement:

1. update this master roadmap;
2. update the active phase-status document;
3. add/update an ADR if architectural;
4. add/update migration documentation if compatibility is affected;
5. only then treat the change as part of the tracked phase.

## Branch Policy

`main` and `dev` remain untouched. Each phase/sub-phase uses a dedicated `feature/*` branch. Later phase branches start from the latest reviewed phase branch unless the roadmap explicitly records an exception.

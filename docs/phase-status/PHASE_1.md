# Phase 1 — SDK/Core Separation

**Status:** In progress
**Branch:** `feature/phase-1-sdk-core-separation`
**Base:** `feature/phase-0-architecture-contract`
**Main/dev:** untouched

## Objective

Make NeuraHive a genuine reusable SDK rather than a platform with an embedded SDK.

## Implemented in this branch

- Introduced the independent `neurahive` package namespace.
- Added dependency-injected `Agent`, `AgentConfig`, `AgentContext`, `AgentResult`, and `AgentRuntime` contracts.
- Added provider-neutral `Model`, `ModelProvider`, and `MemoryProvider` protocols.
- Added instance-scoped `Tool` and `ToolRegistry` contracts.
- Added public API exports from `neurahive`.
- Included `neurahive*` in the package build without removing legacy `agentfactory*`.
- Added core contract tests and a mechanical core/platform import boundary test.

## Deliberately not implemented yet

- Migration of the legacy `RunnableAgent` execution loop.
- Provider adapters for Gemini/OpenAI/Anthropic.
- SQLite/PostgreSQL/Redis memory implementations behind `MemoryProvider`.
- MCP integration adapters.
- Platform dependency resolution.
- Workflow engine.
- Destructive rename of the PyPI distribution.

Those are separate migration steps and must not be coupled into the first core boundary extraction.

## Architectural rule enforced

```text
Project / Platform
        ↓
construct dependencies
        ↓
NeuraHive public contracts
        ↓
platform-independent runtime
```

The core must not discover dependencies through the platform database, Studio, or global registries.

## Exit criteria

Phase 1 is complete only when:

- the core package can be installed/imported independently of Studio dependencies;
- public core tests run without platform DB initialization;
- model, tool, memory, MCP, and policy dependencies are injectable;
- legacy AgentFactory remains usable through an explicit compatibility surface;
- an external example project can create and execute an agent using only public NeuraHive APIs;
- packaging/build checks pass.

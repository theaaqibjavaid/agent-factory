# ADR-0001 — NeuraHive Core / Platform Boundary

- **Status:** Accepted
- **Phase:** 0
- **Date:** 2026-08-18

## Context

The current repository contains both reusable agent SDK primitives and an application platform. The platform has users, workspaces, database state, API routes, Studio services, marketplace registrations, and operational services. The SDK is intended to become a reusable pip-installed runtime that can be embedded in Mausam or unrelated client projects.

The current runtime still resolves some tools, skills, model connections, and run events through `agentfactory.app` database state. That coupling prevents the runtime from being a genuinely reusable engine.

## Decision

NeuraHive will use a strict dependency direction:

```text
Consumer Project / Platform / Studio
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

The reverse dependency is prohibited:

```text
Core -> Platform DB
Core -> Studio UI
Core -> Mausam
Core -> Client application
```

The platform may resolve persisted configuration and construct/inject providers. The core receives those dependencies explicitly and executes without knowing where they came from.

## Responsibilities

### Core

- Agent lifecycle and execution
- Tool contracts and registries
- Model/provider contracts
- Memory contracts
- Skills and plugins
- Workflow and orchestration contracts
- Policies and permissions
- Verification
- MCP interfaces
- Events/tracing contracts
- Core validation and exceptions

### Platform

- users, organizations, workspaces
- authentication and RBAC
- database/persistence
- API routes
- marketplace catalog
- billing/accounting
- operational notifications
- platform-specific dependency resolution

### Studio

- UI/UX for configuring and operating the system
- visualization of workflows/runs/events
- approvals and operational controls

Studio is a consumer of the public API, not a dependency of the core SDK.

## Consequences

### Positive

- Mausam can install NeuraHive without inheriting the platform.
- Client projects can define agents/workflows without modifying core source.
- Provider implementations become replaceable.
- Studio can evolve independently.
- Core tests can run without platform database state.

### Negative

- More explicit interfaces and dependency injection are required.
- Existing platform runtime code must be migrated.
- Some legacy imports and APIs need compatibility adapters.
- The migration will temporarily contain both legacy and v2 paths.

## Rejected alternative

**Keep the current platform-centric runtime and expose more configuration.**

Rejected because configuration alone does not remove runtime coupling to platform persistence and Studio services.

## Acceptance test

A separate repository must be able to install NeuraHive, construct an agent with injected model/tool/memory/policy dependencies, execute it, and define a workflow without importing `neurahive.platform` internals or changing NeuraHive source.

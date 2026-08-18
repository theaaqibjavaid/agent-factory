# NeuraHive v2 — Master Roadmap

> **Status:** Architecture/planning baseline
> **Branch:** `feature/neurahive-v2-roadmap-docs`
> **Scope:** SDK, runtime, workflows, orchestration, plugins, platform boundary, Studio, packaging, security, and developer experience.

## 1. Product Vision

**NeuraHive is the runtime and SDK for building programmable intelligent systems.**

A consuming project installs NeuraHive as a package and defines its own agents, tools, skills, memory providers, policies, models, and workflows outside the NeuraHive core. Creating a new agent or client-specific agentic workflow must never require modifying NeuraHive source.

The core promise is:

> **Install NeuraHive. Compose intelligent systems outside the core. Upgrade the engine independently.**

Examples:

- Mausam can install NeuraHive and define weather, agriculture, tourism, and disaster agents.
- A CRM client can install the same package and define sales, support, research, and reporting agents.
- A third project can define an entirely different workflow without changing NeuraHive.

## 2. Non-Negotiable Architectural Rules

1. **Core is project-agnostic.** NeuraHive must not contain Mausam/client-specific logic.
2. **Public contracts before implementations.** Consumers depend on stable interfaces, not internal modules.
3. **SDK first.** Studio and platform services consume the SDK; the SDK must not depend on Studio.
4. **Configuration over modification.** Agent identity, tools, policies, models, memory, and limits are declarative where practical.
5. **Dependency injection over platform lookups.** Runtime receives resolved dependencies rather than querying platform databases.
6. **Providers are replaceable.** Models, memory, tool execution, and persistence are interfaces with interchangeable implementations.
7. **Native structured tool calling is canonical.** Text/regex/XML tool-call parsing is compatibility-only and eventually deprecated.
8. **Security is explicit.** Trusted local execution and untrusted tool execution are different threat models.
9. **Workflows are first-class.** An agent is a worker; a workflow is a coordinated system of workers.
10. **Every phase must preserve backward compatibility where feasible, with explicit migration paths when it cannot.**

## 3. Target Architecture

```text
                         NeuraHive SDK
                              |
       +----------------------+----------------------+
       |                      |                      |
     Agents               Workflows               Models
       |                      |                      |
       |                 +----+----+             +---+---+
       |                 |         |             |       |
       |               Tasks     Orchestration  Providers Router
       |                 |         |             |       |
       +-----------------+---------+-------------+-------+
                         |
                      Runtime
                         |
          +--------------+--------------+
          |              |              |
        Tools          Memory         Skills
          |              |              |
          +--------------+--------------+
                         |
                    Policies / MCP
                         |
                     Execution
```

Optional consumers:

```text
                     NeuraHive SDK
                          ^
              +-----------+-----------+
              |           |           |
            Studio       CLI       Client App
              |           |           |
           Platform     Project     Project
```

## 4. Phase Plan

### Phase 0 — Architecture Contract

**Priority:** P0  
**Goal:** Freeze boundaries before feature expansion.

Deliverables:

- Public API inventory.
- Core/platform/Studio boundary document.
- Extension contract.
- Dependency-direction rules.
- Compatibility policy.
- Naming and package conventions.
- Architecture decision records for major boundaries.

Definition of done:

- A new project can be described without adding project code to the core.
- No core module requires `agentfactory.app`/platform database state to execute an agent.
- Public versus internal APIs are documented.

---

### Phase 1 — SDK/Core Separation

**Priority:** P0  
**Goal:** Make NeuraHive a genuine reusable SDK rather than a platform with an embedded SDK.

Target areas:

- `base_agent.py` → Agent/Runtime contracts.
- `base_tools.py` → Tool contracts and schema system.
- `llm_manager.py` → model/provider interfaces.
- `memory.py` → memory provider interface.
- `skill.py` → skill contract.
- `mcp_integration.py` → MCP provider/interface.
- `verifier.py` → verification interface.
- `runtime.py` → platform-independent runtime.
- `app/*` → platform-only.
- `web/*` → Studio-only.

Key rule:

```text
Platform resolves dependencies -> Core receives dependencies -> Runtime executes
```

not:

```text
Runtime -> Platform DB -> discover dependencies -> execute
```

Definition of done:

- `pip install neurahive` can provide the core runtime without Studio dependencies.
- A consumer project can instantiate an agent using only public APIs.
- Core unit tests run without the platform database.

---

### Phase 2 — Agent API v2

**Priority:** P0  
**Goal:** Make agent creation configuration-first and stable.

Target API concepts:

```python
Agent(
    name="weather_intelligence",
    instructions="...",
    model="...",
    tools=[...],
    memory=...,
    policy=...,
)
```

Configuration must support:

- identity
- instructions
- model requirements
- fallback policy
- tools
- skills
- memory
- permissions
- budget
- iteration limits
- context policy
- output schema
- delegation policy
- verification policy

Definition of done:

- New agents require no core changes.
- Python and declarative configuration can express the same agent model.
- Agent configuration is validated before execution.

---

### Phase 3 — Tool System v2

**Priority:** P0  
**Goal:** Establish a stable, typed, policy-aware tool contract.

Every tool should expose:

- identity
- description
- input schema
- output schema
- permissions
- safety level
- timeout
- retry policy
- cost metadata
- executor

Required capabilities:

- built-in tools
- project tools
- decorator-based tools
- MCP tools
- plugin-provided tools
- typed schemas
- permission checks
- normalized tool results

Definition of done:

- Tool contract tests exist.
- Input and output schemas are enforced.
- Tool execution is policy-gated.
- Global registry is compatibility-only; dependency-injected registries are canonical.

---

### Phase 4 — Runtime and Native Tool Calling

**Priority:** P0  
**Goal:** Make the execution loop provider-agnostic and structurally correct.

Canonical loop:

```text
LLM -> structured tool call -> schema validation -> policy -> approval -> execute -> result -> LLM
```

Legacy JSON/XML/text parsing may remain temporarily for compatibility but must be isolated and marked deprecated.

Definition of done:

- Native structured tool calling is the default path.
- Tool calls are validated before execution.
- Runtime does not inspect platform database state.
- Run lifecycle and cancellation semantics are defined.

---

### Phase 5 — Model Layer and Routing

**Priority:** P1  
**Goal:** Separate model requirements from concrete provider/model selection.

Introduce:

- `Model`
- `ModelProvider`
- `ModelCatalog`
- `ModelRouter`
- capability descriptors
- pricing metadata
- availability metadata

Capabilities may include:

- tool calling
- structured output
- reasoning
- vision
- streaming
- context window
- latency class
- cost class

Definition of done:

- Agents can request capabilities instead of hard-coding providers.
- Pricing is configuration/catalog data, not stale constants in runtime code.
- Failover remains supported through the provider abstraction.

---

### Phase 6 — Memory Provider Architecture

**Priority:** P1  
**Goal:** Make memory replaceable.

Target interface:

```text
MemoryProvider
  + remember
  + recall
  + search
  + forget
  + export/import where supported
```

Reference implementations:

- in-memory
- SQLite
- PostgreSQL
- Redis
- vector-backed provider
- custom provider

Definition of done:

- Runtime depends only on the interface.
- Provider contract tests exist.
- Project memory can be selected without core changes.

---

### Phase 7 — Skills and Plugin Contracts

**Priority:** P1  
**Goal:** Make reusable capabilities independently composable.

Skill contract:

- metadata
- version
- instructions
- tools
- dependencies
- compatibility
- permissions

Plugin contract may contribute:

- agents
- tools
- skills
- workflows
- model providers
- memory providers
- lifecycle hooks

Definition of done:

- A project can package its capabilities independently.
- Plugin loading has version/compatibility checks.
- Plugin permissions are explicit.

---

### Phase 8 — Policy and Permissions Engine

**Priority:** P1  
**Goal:** Establish a central authorization decision before autonomous execution grows.

Policies must be able to govern:

- network destinations
- filesystem paths
- shell execution
- tool allow/deny lists
- delegation
- workflow actions
- secrets
- approvals
- budgets

Execution rule:

```text
Agent -> Policy Engine -> allow / deny / approval-required -> Executor
```

Definition of done:

- All privileged tool actions are policy-gated.
- Policies are testable independently of agents.
- Approval requirements are represented as structured decisions.

---

### Phase 9 — Workflow Engine

**Priority:** P1  
**Goal:** Make arbitrary agentic workflows first-class.

Core objects:

```text
Workflow
Task
Dependency
Condition
RetryPolicy
TimeoutPolicy
WorkflowContext
WorkflowResult
```

Required patterns:

- sequential
- parallel
- conditional
- retry
- loop/replanning
- human approval
- fan-out/fan-in
- timeout/cancellation

Definition of done:

- Workflows can be defined outside core source.
- DAG validation prevents invalid dependency graphs.
- Task outputs can become inputs to downstream tasks.
- Failures and retries are deterministic and observable.

---

### Phase 10 — Multi-Agent Orchestration

**Priority:** P1  
**Goal:** Coordinate agents without hard-coding project-specific teams.

Patterns:

- supervisor/worker
- hierarchical
- peer collaboration
- reviewer
- delegation
- parallel specialist agents
- handoff

Required controls:

- delegation permissions
- max depth
- max agents
- budget
- timeout
- shared versus isolated memory
- workflow-scoped context

Definition of done:

- A project can create an arbitrary multi-agent workflow without modifying NeuraHive.
- Agent-to-agent communication uses explicit task/context contracts.
- Orchestration is independent of Studio.

---

### Phase 11 — Durable Task State and Events

**Priority:** P1  
**Goal:** Make workflows restartable, observable, and auditable.

Task states:

`PENDING`, `READY`, `RUNNING`, `WAITING`, `APPROVAL_REQUIRED`, `SUCCEEDED`, `FAILED`, `CANCELLED`, `RETRYING`.

Events should include:

- AgentStarted/Completed/Failed
- WorkflowStarted/Completed/Failed
- TaskStarted/Completed/Failed
- ModelCalled/Completed
- ToolCalled/Completed/Failed
- MemoryRead/Written
- ApprovalRequested/Granted/Denied

Definition of done:

- Every execution has a traceable workflow/task/run identity.
- State can survive process restart where the selected persistence backend supports it.
- Events are consumable by Studio, logging, billing, and integrations without coupling the core to those consumers.

---

### Phase 12 — Worker/Execution Architecture

**Priority:** P2  
**Goal:** Support long-running and concurrent execution.

Evolution:

```text
Current: in-process worker
Future: API -> queue -> worker pool -> runtime
```

Possible future implementations may use Redis and a worker framework, but the queue/executor interface must be defined before choosing infrastructure.

Definition of done:

- Long-running tasks don't block the API process.
- Retries are durable.
- Concurrent workflows are isolated.
- Worker implementation is replaceable.

---

### Phase 13 — Strong Sandbox Boundary

**Priority:** P2  
**Goal:** Safely execute untrusted tools.

Trusted developer tools may execute locally under policy controls.

Untrusted marketplace/client-supplied tools must eventually execute in isolated workers/containers with:

- CPU limits
- memory limits
- timeouts
- filesystem scope
- network policy
- environment isolation
- secret allowlists

Definition of done:

- Documentation clearly distinguishes trusted execution from sandboxed execution.
- No in-process AST restriction is represented as a full security boundary.
- Sandbox integration is replaceable.

---

### Phase 14 — CLI and Project Scaffolding

**Priority:** P1  
**Goal:** Make creating a new project take minutes.

Target commands:

```text
neurahive create-project <name>
neurahive agent create <name>
neurahive workflow create <name>
neurahive run
neurahive studio
neurahive doctor
```

Generated project:

```text
project/
  agents/
  tools/
  skills/
  workflows/
  policies/
  config/
  tests/
  pyproject.toml
```

Definition of done:

- A new developer can create and run an agent without reading internal source.
- Generated projects depend only on public APIs.

---

### Phase 15 — Studio as SDK Consumer

**Priority:** P1  
**Goal:** Reverse the dependency direction.

Target:

```text
NeuraHive SDK
      ^
      |
   Studio / API / CLI / Client apps
```

Studio should use the same public agent, workflow, tool, model, memory, policy, event, and execution contracts available to external projects.

Definition of done:

- Studio does not require internal runtime shortcuts that external projects cannot use.
- Platform persistence adapters resolve dependencies and pass them into core.
- SDK can be used without Studio.

---

### Phase 16 — Contract Testing and Compatibility

**Priority:** P1

Every public provider interface gets a shared contract suite:

- ToolProvider
- MemoryProvider
- ModelProvider
- WorkflowRunner
- Plugin
- Policy
- Event sink
- Sandbox executor

Definition of done:

- Every built-in implementation passes the same contract tests.
- Public API changes require compatibility review.
- Migration notes exist for breaking changes.

---

### Phase 17 — Examples and Reference Implementations

**Priority:** P1

Provide independent examples proving the core is generic:

```text
examples/
  coding_agent/
  research_agent/
  customer_support/
  mausam_style/
```

The examples must live outside core runtime modules.

Definition of done:

- At least three unrelated projects use only public NeuraHive APIs.
- One example demonstrates a multi-agent workflow.
- One example demonstrates a custom tool/plugin.

---

### Phase 18 — Packaging and Release Engineering

**Priority:** P1

Target distribution:

```text
neurahive
```

Target import:

```python
import neurahive
```

Target CLI:

```text
neurahive
```

Optional extras should keep the base SDK small:

```text
neurahive[gemini]
neurahive[openai]
neurahive[anthropic]
neurahive[platform]
neurahive[studio]
```

Definition of done:

- Clean package installation in a fresh environment.
- Minimal base install does not require Studio/platform dependencies.
- Versioning, changelog, release artifacts, and migration policy are documented.

---

## 5. Current Repository Mapping

| Current area | v2 direction |
|---|---|
| `base_agent.py` | Refactor into public Agent + runtime contracts |
| `base_tools.py` | Retain concepts; strengthen schemas and dependency injection |
| `llm_manager.py` | Split Model, Provider, Router, Catalog |
| `memory.py` | Introduce `MemoryProvider` and adapters |
| `skill.py` | Formalize Skill/Plugin contract |
| `mcp_integration.py` | Keep as MCP adapter behind public interface |
| `verifier.py` | Generalize into Verification contracts |
| `runtime.py` | Remove platform DB coupling; make dependency-injected |
| `app/*` | Platform-only services |
| `web/*` | Studio consumer |
| engineering crew | Move toward examples/reference project |
| global tool registry | Compatibility layer; injected registry becomes canonical |
| custom tool sandbox | Defense-in-depth now; isolated execution later |
| tests | Split core contract tests from platform tests |

## 6. Critical Refactor Identified by Audit

The current runtime resolves platform registrations directly. This violates the intended reusable-SDK boundary.

Target:

```python
runtime = AgentRuntime(
    agent=agent_definition,
    model=model_provider,
    tools=tool_registry,
    memory=memory_provider,
    policy=policy,
)
```

The runtime must not perform platform database lookups to discover tools, skills, or model connections.

## 7. What We Will Not Do Yet

- Do not clone Ruflo.
- Do not introduce Kubernetes before workflow semantics are stable.
- Do not replace SQLite simply because PostgreSQL/Redis may be useful later.
- Do not add multiple vector databases before the provider contract exists.
- Do not make Studio mandatory.
- Do not expose LangChain as the NeuraHive public API.
- Do not build a large autonomous swarm before the SDK and policy boundaries are stable.

## 8. Acceptance Test for the Entire Architecture

The definitive test is:

> **Can Mausam implement its entire agent layer in a separate project using only the published NeuraHive API, without importing NeuraHive internals or modifying NeuraHive source?**

Then repeat the same test with an unrelated client project.

If both pass, NeuraHive has achieved its original purpose.

## 9. Milestones

| Milestone | Acceptance criterion |
|---|---|
| M1 | Architecture boundary frozen |
| M2 | External project defines one agent |
| M3 | External project defines arbitrary tools |
| M4 | External project selects model/memory providers |
| M5 | External project installs/defines skills |
| M6 | External project defines a workflow |
| M7 | External project runs multi-agent workflows |
| M8 | Workflow state survives supported restart scenarios |
| M9 | Untrusted tools can run in an isolated executor |
| M10 | Studio operates through public SDK contracts |
| M11 | Mausam agent package works without core modification |
| M12 | Independent client project works without core modification |

## 10. Working Rule

All implementation work for this roadmap must be done on dedicated `feature/*` branches. Never develop directly on `main` or `dev`.

Every completed phase should produce:

1. implementation
2. tests
3. documentation update
4. migration note if applicable
5. changelog entry where user-facing
6. PR into the agreed integration branch

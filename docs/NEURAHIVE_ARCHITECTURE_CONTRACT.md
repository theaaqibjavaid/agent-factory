# NeuraHive Architecture Contract

> **Purpose:** The architectural constitution for NeuraHive v2.

## 1. Identity

NeuraHive is a reusable Python SDK/runtime for programmable intelligent systems. It is not a single application and it is not a collection of project-specific agents.

A consumer installs NeuraHive and composes its own intelligent system outside the package.

## 2. Dependency Direction

The only permitted direction is:

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

The reverse dependency is prohibited:

```text
Core Runtime -> Platform DB
Core Runtime -> Studio UI
Core Runtime -> Mausam
Core Runtime -> Client application
```

## 3. Core Responsibilities

The core may own:

- Agent abstraction and lifecycle
- Agent context
- Runtime/execution loop
- Tool contracts and registries
- Model/provider abstractions
- Memory interfaces
- Skills
- Workflows
- Orchestration
- Policies and permissions
- Verification
- MCP interfaces/adapters
- Events/tracing contracts
- Plugin contracts
- Core exceptions and validation

## 4. Platform Responsibilities

The optional platform may own:

- users
- organizations
- workspaces
- authentication
- RBAC
- persistent platform configuration
- API routes
- marketplace catalog
- database adapters
- billing/accounting
- Studio services
- terminal services
- platform notifications

The platform resolves configuration and injects dependencies into the core.

## 5. Studio Responsibilities

Studio is a consumer of the SDK.

Studio may provide:

- agent editor
- workflow editor
- tool/skill/MCP management
- observability
- approvals
- configuration UI
- operational dashboards

Studio must not become a required dependency of the SDK.

## 6. Project Responsibilities

A consuming project owns:

- project agents
- prompts/instructions
- project tools
- project skills
- project workflows
- project policies
- project integrations
- project memory choices
- project model choices

Example:

```text
mausam-agents/
  agents/
  tools/
  skills/
  workflows/
  policies/
  config/
```

No project-specific code belongs in the NeuraHive core.

## 7. Public API Rule

A module is not a supported public API merely because it can be imported.

Public APIs must be:

- explicitly exported
- documented
- contract-tested
- versioned
- migration-aware

Internal modules may change without consumer compatibility guarantees.

## 8. Dependency Injection Rule

Runtime components receive their dependencies.

Preferred:

```python
AgentRuntime(
    agent=agent,
    model=model_provider,
    tools=tool_registry,
    memory=memory_provider,
    policy=policy,
)
```

Forbidden architectural pattern:

```python
# Runtime reaches into platform state to discover dependencies.
platform_db.find_tools(...)
platform_db.find_model(...)
```

## 9. Provider Rule

Replaceable infrastructure must use provider interfaces.

Required provider families:

- model
- memory
- tool execution
- workflow persistence
- event sinks
- sandbox execution

A built-in implementation is a provider, not the definition of the abstraction.

## 10. Agent Rule

Agents are configurations plus runtime behavior.

An agent definition may specify:

- identity
- instructions
- model requirements
- tools
- skills
- memory
- policies
- budgets
- iteration limits
- delegation rules
- verification rules
- output schema

Creating a new agent must not require subclassing or editing NeuraHive core source unless the consumer is implementing a genuinely new runtime primitive.

## 11. Tool Rule

Every tool must expose a structured contract:

```text
identity
input schema
output schema
permissions
safety level
timeout
retry policy
cost metadata
executor
```

Execution must pass through policy checks.

## 12. Tool Calling Rule

Native structured tool calling is canonical.

Legacy text/JSON/XML parsing may exist only as a compatibility path and must not define the modern execution architecture.

## 13. Workflow Rule

A workflow is a first-class graph of tasks.

A task may invoke:

- an agent
- a tool
- a sub-workflow
- a human approval step
- a system operation

Workflows must support dependency validation, retries, timeouts, cancellation, conditions, and observable state.

## 14. Multi-Agent Rule

Multi-agent behavior is built using workflows and orchestration contracts, not project-specific hard-coded supervisor logic inside the core.

Supported patterns should eventually include:

- supervisor/worker
- hierarchical
- parallel specialists
- reviewer
- delegation
- handoff
- fan-out/fan-in

## 15. Security Rule

There are two execution trust levels:

### Trusted

Developer-controlled code may use local execution subject to policy and defensive validation.

### Untrusted

Marketplace/client-supplied code must use an isolated executor once supported.

AST validation, restricted builtins, or in-process checks must never be documented as equivalent to a process/container security boundary.

## 16. Memory Rule

Agents depend on `MemoryProvider`, not a specific storage technology.

Reference providers may include SQLite, PostgreSQL, Redis, and vector-backed storage.

## 17. Model Rule

Agents should express model requirements where possible rather than binding the entire system to one provider.

Model routing may consider:

- capabilities
- context window
- reasoning
- tool calling
- structured output
- latency
- availability
- cost

## 18. Event Rule

Execution emits structured events independent of their consumers.

Studio, logging, billing, analytics, notifications, and integrations consume events; the core must not depend on those consumers.

## 19. Testing Rule

Every public provider interface receives contract tests.

Examples:

```text
MemoryProviderContract
ModelProviderContract
ToolProviderContract
WorkflowRunnerContract
PolicyContract
PluginContract
```

All built-in implementations must pass the relevant contracts.

## 20. Release Rule

Every feature branch must contain its implementation and required tests. User-facing changes require documentation updates. Breaking changes require migration notes.

## 21. Branch Rule

Development must happen on `feature/*` branches.

- Never commit feature work directly to `main`.
- Never commit feature work directly to `dev`.
- Feature branches should start from the current integration base agreed for the work.
- Completed work should be reviewed through a pull request.

## 22. Final Architectural Test

NeuraHive is successful when an unrelated repository can:

```bash
pip install neurahive
```

and define its own agents, tools, skills, memory, policies, models, and workflows using only public APIs, with **zero modifications to NeuraHive source**.

Mausam is one validation project, not a special case.

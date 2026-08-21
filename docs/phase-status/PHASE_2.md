# Phase 2 — Agent API v2

**Status:** In progress  
**Branch:** `feature/phase-2-agent-api-v2`  
**Protected branches:** `main` and `dev` — untouched

## Objective

Create the stable, configuration-first NeuraHive Agent API.

An agent must be definable by a consuming project without modifying NeuraHive source or depending on platform internals.

## Scope

- validated agent identity
- instructions/system behavior
- model requirements and fallback declarations
- tool and skill requirements
- memory requirements
- permissions and budget declarations
- context/delegation constraints
- verification requirements
- explicit execution dependency injection
- serialization-safe configuration

## Architecture refinement

Phase 1 established a minimal `AgentConfig`.

Phase 2 expands it with **declarative requirement objects**, rather than provider-specific runtime objects.

Target composition:

```text
Agent
├── AgentConfig
│   ├── Identity
│   ├── ModelRequirement
│   ├── ToolRequirement
│   ├── SkillRequirement
│   ├── MemoryRequirement
│   ├── PermissionSet
│   ├── Budget
│   ├── DelegationPolicy
│   └── VerificationPolicy
└── injected runtime dependencies

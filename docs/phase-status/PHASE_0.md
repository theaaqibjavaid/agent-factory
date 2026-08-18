# Phase 0 — Architecture Contract Execution Record

**Status:** In progress  
**Branch:** `feature/phase-0-architecture-contract`  
**Base:** `feature/neurahive-v2-roadmap-docs`  
**Main/dev:** untouched

## Objective

Freeze the NeuraHive v2 architecture before implementing the SDK/core separation.

## Completed in this branch

- Added the NeuraHive public API inventory and compatibility classification.
- Added ADR-0001 for the core/platform boundary.
- Added an ADR index and ADR rules.
- Added a Phase 0 acceptance gate.
- Updated the documentation index.
- Updated contribution guidance so all feature work uses dedicated `feature/*` branches and never writes directly to `main`/`dev`.

## Current architectural finding

The repository is **not yet core/platform separated**. The current package still mixes SDK primitives with platform/runtime concerns. In particular, the current platform runtime resolves persisted tools, skills, model connections, and run events through `agentfactory.app` database services.

That is recorded as a known Phase 1 implementation target rather than hidden behind documentation.

## Remaining Phase 0 work

1. Label the existing architecture documentation explicitly as current/legacy where necessary.
2. Define the v2 migration/compatibility strategy for the `agentfactory` package and target `neurahive` package.
3. Add an executable dependency-boundary gate once the target core package structure is introduced.
4. Add public-import smoke tests for the target API surface.
5. Add a core-only test command that does not initialize platform DB state.
6. Record additional ADRs for package boundaries and provider injection if implementation introduces material alternatives.
7. Update the master roadmap's Phase 0 status before opening the Phase 0 PR.

## Exit criteria

Phase 0 is complete only when the architecture contract is both documented and mechanically enforceable. Phase 1 begins only after this branch has a reviewable PR and the Phase 0 acceptance checklist is satisfied.

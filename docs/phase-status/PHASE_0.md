# Phase 0 — Architecture Contract Execution Record

**Status:** Implementation gate established; Phase 0 remains open pending review and final acceptance.  
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
- Added the `neurahive/` v2 core namespace boundary.
- Added an executable source-level dependency-boundary test.
- Added the v1 → v2 package/API compatibility strategy.
- Explicitly labeled the existing architecture documentation as current/legacy versus v2 target architecture.

## Current architectural finding

The repository is **not yet fully core/platform separated**. The existing `agentfactory` package still mixes SDK primitives with platform/runtime concerns. In particular, the current platform runtime resolves persisted tools, skills, model connections, and run events through platform services.

This remains a deliberate Phase 1 implementation target rather than being hidden behind documentation.

## Remaining gates

1. Introduce the actual v2 public runtime contracts and provider interfaces in Phase 1.
2. Add public-import smoke tests for those contracts.
3. Add a core-only test command that does not initialize platform DB state.
4. Run the full regression suite after the first core/runtime extraction.
5. Run lint/type/security checks required by CI.
6. Update the master roadmap when Phase 0 is formally accepted.
7. Complete review through a pull request before integration.

## Exit criteria

Phase 0 is complete only when the architecture contract is documented, the boundary is mechanically enforceable, and the branch has received review. Phase 1 begins only after the Phase 0 acceptance checklist is satisfied.

# NeuraHive v2 — Phase 0 Acceptance Checklist

> This is the implementation gate for Phase 0. Phase 1 must not be treated as complete until these architectural controls are explicit.

## Documentation

- [x] Master v2 roadmap exists.
- [x] Architecture contract exists.
- [x] Public API inventory exists.
- [x] Core/platform boundary ADR exists.
- [x] ADR index exists.
- [x] Current architecture document updated to clearly label legacy/current versus target v2 architecture.
- [x] Migration document defines the legacy-to-v2 package/API transition.

## Architecture controls

- [x] Target core package boundary exists as `neurahive/`.
- [x] Core package has no imports from platform/database modules.
- [x] Core package has no imports from Studio/web modules.
- [ ] Runtime receives model/tool/memory/policy dependencies through explicit construction.
- [ ] Platform dependency resolution is outside the core runtime.
- [x] Public exports are centralized and documented.
- [x] Internal modules are not presented as supported API.

## Tests / gates

- [x] Add a dependency-boundary test that fails when core imports platform or Studio modules.
- [ ] Add public-import smoke tests for the documented API once the Phase 1 contracts exist.
- [ ] Add a core-only test command that does not initialize platform DB state.
- [ ] Run the existing full regression suite after boundary changes.
- [ ] Run lint/type/security checks required by CI.

## Naming / packaging

- [x] Target distribution/import/CLI naming is documented as `neurahive`.
- [x] No package rename is performed until the v2 compatibility strategy is ready.
- [x] Existing `agentfactory` imports remain explicitly classified as compatibility during migration.

## Branch policy

- [x] Phase work is performed on a dedicated `feature/*` branch.
- [ ] Phase branch receives a reviewable PR before integration.
- [ ] `main` remains untouched by feature implementation.
- [ ] `dev` remains untouched by feature implementation.

## Exit criteria

Phase 0 is complete only when the architecture is documented **and the repository has executable enforcement** for the core/platform boundary. Documentation alone is not sufficient.

The remaining unchecked items are implementation gates that belong to the Phase 1 core/runtime separation unless they can be completed without prematurely implementing v2 runtime contracts.

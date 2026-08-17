## Summary

What this PR does and why. Link the issue it closes (e.g. `Closes #12`).

## Changes

- Bullet list of the main changes.

## Testing

- [ ] Ran `pytest -q` (full suite green)
- [ ] Coverage gate: `pytest --cov --cov-fail-under=80`
- [ ] `mypy` platform surface: `mypy agentfactory/app agentfactory/runtime.py agentfactory/terminal.py agentfactory/validation.py agentfactory/custom_tools.py --follow-imports=skip --ignore-missing-imports`
- [ ] `ruff check --select F821 agentfactory tests`
- [ ] UI (if touched): `cd web && bun tsc -b --noEmit && bun run build`

**Every code change ships with tests** (new behavior → new tests; bug fix →
regression test).

## Notes for reviewers

Anything specific to look at, decisions made, or follow-up work.

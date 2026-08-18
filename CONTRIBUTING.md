# Contributing to NeuraHive

> The repository is transitioning from AgentFactory to NeuraHive v2. Feature work must follow the v2 architecture and branch policy.

## Development setup

Requirements: Python 3.10–3.12, `git`, and `pip`.

```bash
git clone https://github.com/theaaqibjavaid/agent-factory.git
cd agent-factory
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

## Running tests

```bash
pytest -q
pytest tests/test_mcp_client.py -q
```

Every bug fix or refactor must ship with regression tests. Architecture changes must also update the relevant NeuraHive v2 documentation and, where applicable, an ADR.

## Linting & static checks

```bash
ruff check --select F821 agentfactory tests
```

CI runs the repository's configured test, lint, type, security, coverage, package-build, and Studio checks.

## Architecture rules

Read these before implementing v2 work:

- `docs/NEURAHIVE_V2_ROADMAP.md` — source of truth for future architecture work.
- `docs/NEURAHIVE_ARCHITECTURE_CONTRACT.md` — non-negotiable architecture rules.
- `docs/NEURAHIVE_PUBLIC_API.md` — public/compatibility/internal API classification.
- `docs/adr/` — architectural decisions.
- `docs/NEURAHIVE_PHASE_0_ACCEPTANCE.md` — Phase 0 gate.

The core must remain project-agnostic. New agents, tools, skills, memory providers, policies, models, and workflows belong in consuming projects or extension packages, not in NeuraHive core source.

## Branch policy

**Never commit feature work directly to `main` or `dev`.**

Every phase/task gets its own `feature/*` branch. Branch from the agreed integration base, keep the branch focused, and open a PR when the phase is reviewable.

Examples:

```bash
git checkout dev
git pull
git checkout -b feature/phase-1-sdk-core-separation
```

For follow-on phases, the base may be the reviewed phase branch when explicitly agreed. Do not silently rewrite or merge `main`/`dev` from feature work.

## Contribution workflow

1. Select the phase/task from the NeuraHive v2 roadmap.
2. Create a dedicated `feature/*` branch.
3. Inspect existing implementation and tests before changing architecture.
4. Implement the smallest coherent slice of the phase.
5. Add/update tests and documentation.
6. Run the relevant checks.
7. Update roadmap/acceptance status.
8. Open a reviewable PR.

## Naming during migration

The target project identity is **NeuraHive**. The current repository and Python package still contain legacy `agentfactory` names during migration. Do not perform a broad package/repository rename as part of an unrelated feature. Naming migration must have its own planned phase and compatibility strategy.

## Project layout

- `agentfactory/` — current implementation during migration.
- `docs/` — current documentation plus the NeuraHive v2 architecture/roadmap.
- `tests/` — unit, integration, regression, and future contract tests.
- `web/` — current Studio implementation.

## Reporting issues

Include Python version, relevant environment details, the failing command, and a minimal reproduction. Security issues must be reported privately according to `SECURITY.md`.

# Contributing to AgentFactory

Thanks for contributing! AgentFactory is a universal, self-hostable AI agent
framework. This guide covers local development, testing, and the contribution
workflow.

## Development setup

Requirements: Python 3.10–3.12, `git`, and `pip`.

```bash
# Clone and install (editable, with dev/test dependencies)
git clone https://github.com/theaaqibjavaid/agent-factory.git
cd agent-factory
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -e '.[dev]'             # or: pip install -r requirements.txt pytest pytest-asyncio httpx PyJWT ruff

# Copy env template (optional; the SDK runs without it)
cp .env.example .env                # then add your LLM API keys
```

## Running tests

```bash
pytest -q                           # full suite
pytest tests/test_mcp_client.py -q  # a single file
```

**Every bug fix or refactor must ship with regression tests.** The Phase 0
audit-fix test files (`tests/test_base_agent.py`, `tests/test_worker.py`,
`tests/test_approval_server.py`, `tests/test_cli.py`, `tests/test_mcp_client.py`)
are the template to follow.

## Linting & static checks

```bash
ruff check --select F821 agentfactory tests   # undefined names (CI gate)
# Full lint config lives in pyproject.toml [tool.ruff]; the codebase has
# pre-existing findings outside F821 that are tracked as cleanup work.
```

CI (`.github/workflows/ci.yml`) runs on Python 3.10/3.11/3.12:
- `ruff check --select F821`
- `pytest`
- wheel build + fresh-venv `pip install` smoke test (`agentfactory --version`)

## Code style

- PEP 8, 100-char lines, Google-style docstrings (see `pyproject.toml`).
- Type hints on all public functions/classes.
- Structured logging with `structlog` — no bare `print` in library code.
- New features go through the `@tool` decorator and `ToolRegistry`; no new
  hardcoded agent behavior in `base_agent.py`.

## Contribution workflow

1. Create a feature branch from `main` — never commit directly to `main`/`master`:
   ```bash
   git checkout -b fix/my-bugfix
   ```
2. Make focused changes **with tests**; run the full suite until green.
3. Commit with a descriptive message (imperative, ≤ 72 chars title):
   ```bash
   git add <files>
   git commit -m "Fix proposal id collision when two proposals land in one second"
   ```
4. Push the branch and open a pull request:
   ```bash
   git push -u origin fix/my-bugfix
   ```
5. Keep PRs small and reviewable; reference the issue/phase task in the description.

## Project layout (quick map)

- `agentfactory/` — the SDK: `base_agent.py` (agents), `base_tools.py`
  (`@tool`, registries), `llm_manager.py` (failover/budget), `verifier.py`,
  `memory.py` (SQLite), `skill.py`, `mcp_integration.py`, `app/` (FastAPI
  approval server), `agents/` (worker, config loader), `tools/` (built-ins).
- `docs/` — architecture, PRD, design, security, phases, and guides.
- `tests/` — unit + regression tests (see `docs/AUDIT.md` for fix status).

## Reporting issues

Include: Python version, `pip freeze` output, the failing command, and (for
bugs) a minimal reproduction. Security issues: see `docs/security.md` and
report privately rather than opening a public issue.

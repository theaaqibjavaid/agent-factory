# Verifier

The Verifier performs post-execution verification and audit on agent changes. It uses **strict context pruning** to keep output concise.

## Features

- **Context pruning**: Extracts only failing lines + ±2 lines of context
- **Multiple check types**: Tests, linting, security scans, custom checks
- **Audit reports**: Structured JSON reports with pass/fail status
- **Budget-aware**: Only runs checks relevant to the changes made

## Core Classes

### `Verifier`

Main verification orchestrator.

```python
from agentfactory.verifier import Verifier

verifier = Verifier()
verifier.add_check(name="pytest", command="pytest tests/", timeout=120)
verifier.add_check(name="lint", command="ruff check .", timeout=30)
verifier.add_check(name="security", command="ruff check --select S .", timeout=30)
```

### `VerificationReport`

Structured report with all check results.

```python
report = verifier.run(repo_path=".")
print(report.to_dict())
# {
#   "feature_name": "feature-branch",
#   "branch_name": "feature/my-feature",
#   "overall_passed": True,
#   "checks": [
#     {
#       "name": "pytest",
#       "passed": True,
#       "message": "All tests passed",
#       "stdout": "...",
#       "stderr": "..."
#     }
#   ]
# }
```

### `AuditResult`

Result of a single check.

| Field | Type | Description |
|-------|------|-------------|
| `name` | str | Check name |
| `passed` | bool | Pass/fail status |
| `message` | str | Human-readable result |
| `stdout` | str | Command stdout (if applicable) |
| `stderr` | str | Command stderr (if applicable) |
| `failed_lines` | list[str] | Failing lines (pruned) |

## Context Pruning

When a check fails, the verifier:
1. Runs the command and captures output
2. Identifies failing lines (e.g., test failures, lint errors)
3. Extracts failing lines + 2 lines of context before/after
4. Discards the rest

This keeps reports under 200 lines even for large codebases.

## Usage

```python
from agentfactory.verifier import Verifier

verifier = Verifier()

# Add checks
verifier.add_check("pytest", "pytest tests/", timeout=120)
verifier.add_check("ruff", "ruff check .", timeout=30)
verifier.add_check("mypy", "mypy agentfactory/", timeout=60)

# Run verification
report = verifier.run(repo_path=".")

# Check results
if not report.overall_passed:
    for check in report.checks:
        if not check.passed:
            print(f"❌ {check.name}: {check.message}")
            for line in check.failed_lines:
                print(f"  {line}")
else:
    print("✅ All checks passed")

# Serialize
json_report = report.to_dict()
```

## Custom Checks

```python
verifier.add_check(
    name="custom-script",
    command="python scripts/my_check.py",
    timeout=60,
    fail_on_stderr=True,  # Treat any stderr output as failure
)
```

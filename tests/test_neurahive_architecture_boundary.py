"""Executable architecture gates for the NeuraHive v2 core boundary.

These tests are intentionally structural: they inspect the source tree without
initializing the platform application or database.
"""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# Target core directories are allowed to expand as Phase 1 introduces them.
CORE_ROOT = ROOT / "neurahive"
FORBIDDEN_IMPORT_PREFIXES = (
    "agentfactory.app",
    "agentfactory.web",
    "neurahive.platform",
    "neurahive.studio",
)


def _imports_from(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_target_core_directory_exists():
    """The v2 core must have a distinct package boundary before Phase 1 proceeds."""
    assert CORE_ROOT.is_dir(), "Create the neurahive/ core package before Phase 1 implementation"
    assert (CORE_ROOT / "__init__.py").is_file()


def test_core_has_no_platform_or_studio_imports():
    """Core modules must never depend on platform/database/Studio modules."""
    violations: list[str] = []
    for path in CORE_ROOT.rglob("*.py"):
        for imported in _imports_from(path):
            if imported.startswith(FORBIDDEN_IMPORT_PREFIXES):
                violations.append(f"{path.relative_to(ROOT)} imports {imported}")
    assert not violations, "Core/platform dependency violation(s):\n" + "\n".join(violations)


def test_legacy_platform_runtime_is_not_present_in_target_core():
    """The legacy platform runtime must remain outside the new core namespace."""
    assert not (CORE_ROOT / "app").exists()
    assert not (CORE_ROOT / "web").exists()


def test_public_api_is_centralized():
    """The target package must define an explicit export surface."""
    init = CORE_ROOT / "__init__.py"
    source = init.read_text(encoding="utf-8")
    assert "__all__" in source

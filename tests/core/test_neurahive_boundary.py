"""Mechanical dependency boundary checks for the NeuraHive core namespace."""

from pathlib import Path


FORBIDDEN_IMPORT_PREFIXES = (
    "agentfactory.app",
    "agentfactory.web",
    "agentfactory.platform",
    "fastapi",
    "sqlalchemy",
    "redis",
)


def test_neurahive_core_has_no_platform_imports():
    root = Path(__file__).parents[2] / "neurahive"
    offenders: list[str] = []

    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for prefix in FORBIDDEN_IMPORT_PREFIXES:
            if f"import {prefix}" in text or f"from {prefix}" in text:
                offenders.append(f"{path}: {prefix}")

    assert not offenders, "NeuraHive core imports platform/runtime dependencies:\n" + "\n".join(offenders)

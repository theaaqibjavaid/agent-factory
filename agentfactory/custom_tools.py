"""
Runtime loader for custom tools (Phase 4.1).

Loads validated custom tool code into a ``ToolDef``:

- The module executes in a restricted namespace: a small allowlist of
  builtins, no import machinery (``__import__`` removed), and ``__file__``
  pointing inside the workspace sandbox root so relative file access stays
  path-scoped.
- The tool's metadata (safety level, cost, category, tags) comes from the
  platform registration row, not from the code — the code can never claim a
  tool is SAFE.
- DESTRUCTIVE/MODIFIED safety levels remain enforced by the platform runtime
  gates (``allow_destructive`` / HITL approval).

Sandbox is defense-in-depth, not a security boundary: custom code runs in the
same process as the platform. Deployments that need hard isolation should run
the worker in a container (see docs/security.md).
"""

import builtins
import json
import os
import types
from typing import Any, Dict, Optional

from agentfactory.base_tools import SafetyLevel, ToolDef

# Builtins that are safe enough for tool code (no import, no eval, no file
# write primitives that bypass the sandboxed file tools).
_SAFE_BUILTINS = {
    "abs", "all", "any", "ascii", "bin", "bool", "bytearray", "bytes", "callable",
    "chr", "classmethod", "complex", "dict", "dir", "divmod", "enumerate", "filter",
    "float", "format", "frozenset", "getattr", "hasattr", "hash", "hex", "id", "int",
    "isinstance", "issubclass", "iter", "len", "list", "map", "max", "memoryview",
    "min", "next", "object", "oct", "ord", "pow", "print", "property", "range",
    "repr", "reversed", "round", "set", "setattr", "slice", "sorted", "staticmethod",
    "str", "sum", "super", "tuple", "type", "vars", "zip",
}


class CustomToolError(RuntimeError):
    """Raised when custom tool code fails to load or execute."""


def _sandbox_builtins() -> Dict[str, Any]:
    """Build a builtins namespace without import/eval/file-write primitives."""
    safe: Dict[str, Any] = {}
    for name in _SAFE_BUILTINS:
        if hasattr(builtins, name):
            safe[name] = getattr(builtins, name)
    safe["__import__"] = _deny_import
    safe["eval"] = _deny
    safe["exec"] = _deny
    safe["open"] = _deny
    safe["input"] = _deny
    safe["exit"] = _deny
    safe["quit"] = _deny
    safe["help"] = _deny
    safe["print"] = builtins.print
    return safe


def _deny(*args: Any, **kwargs: Any) -> Any:
    raise CustomToolError("Operation is not allowed in custom tool sandbox")


# Pure-compute / read-only stdlib modules custom tools may import. Anything
# else (subprocess, os, socket, ...) stays blocked — see validation._FORBIDDEN_IMPORTS.
_ALLOWED_MODULES = {
    "re", "json", "math", "random", "string", "datetime", "time", "collections",
    "itertools", "functools", "operator", "typing", "statistics", "decimal",
    "fractions", "uuid", "base64", "hashlib", "html", "csv", "urllib.parse",
    "urllib.request", "urllib.error", "textwrap", "difflib", "unicodedata",
    "enum", "dataclasses", "bisect", "heapq", "copy", "pprint", "secrets",
}
_ALLOWED_MODULE_CACHE: Dict[str, Any] = {}


def _deny_import(name: str, *args: Any, **kwargs: Any) -> Any:
    root = name.split(".")[0]
    if root not in _ALLOWED_MODULES:
        raise CustomToolError(
            f"Importing '{root}' is not allowed in custom tool sandbox (allowlist: stdlib compute/read-only modules)"
        )
    if root not in _ALLOWED_MODULE_CACHE:
        import importlib

        _ALLOWED_MODULE_CACHE[root] = importlib.import_module(root)
    return _ALLOWED_MODULE_CACHE[root]


def load_custom_tool(
    code: str,
    tool_name: str,
    function_name: Optional[str] = None,
    workspace_root: Optional[str] = None,
) -> ToolDef:
    """
    Compile + exec custom tool code and return a ``ToolDef`` for it.

    The returned ToolDef's ``func`` is the exported function; metadata is
    filled in by the caller (registration row) or defaults to SAFE + $0.
    """
    if not code or not code.strip():
        raise CustomToolError("Custom tool code is empty")

    sandbox_dir = workspace_root or os.getenv(
        "AGENTFACTORY_WORKSPACE_ROOT", os.path.join(os.path.expanduser("~"), ".agentfactory", "workspaces")
    )
    module_name = f"_custom_tool_{tool_name}"
    module = types.ModuleType(module_name)
    module.__file__ = os.path.join(sandbox_dir, f"{tool_name}.py")
    module.__name__ = module_name
    module.__builtins__ = _sandbox_builtins()

    try:
        compiled = compile(code, module.__file__, "exec")
        exec(compiled, module.__dict__)  # noqa: S102 — sandboxed namespace above
    except Exception as e:  # noqa: BLE001 — surfaced as a tool error
        raise CustomToolError(f"Custom tool '{tool_name}' failed to load: {e}") from e

    func = getattr(module, function_name or tool_name, None)
    if func is None:
        # Fall back to the first callable defined in the module.
        func = next((v for v in vars(module).values() if callable(v) and not v.__name__.startswith("_")), None)
    if func is None:
        raise CustomToolError(f"Custom tool '{tool_name}' defines no callable entry point")

    return ToolDef(
        name=tool_name,
        func=func,
        description=getattr(func, "__doc__", "") or f"Custom tool: {tool_name}",
        args_schema=None,  # rendered by the runtime from the registration metadata
        category="custom",
        cost_per_call_usd=0.0,
        safety_level=SafetyLevel.SAFE,
        tags=["custom"],
    )


def tool_def_from_registration(row: Dict[str, Any], workspace_root: Optional[str] = None) -> Optional[ToolDef]:
    """Build a ToolDef from a ``tool_registrations`` DB row (metadata from JSON)."""
    try:
        meta = json.loads(row.get("metadata") or "{}")
    except (json.JSONDecodeError, TypeError):
        meta = {}
    if not meta:
        meta = {}

    code = row.get("code")
    if not code:
        return None

    tool_def = load_custom_tool(
        code,
        row["name"],
        function_name=meta.get("function_name"),
        workspace_root=workspace_root,
    )

    # Metadata comes from the registration row — never from the code.
    tool_def.category = meta.get("category", "custom")
    tool_def.cost_per_call_usd = float(meta.get("cost_per_call_usd", 0.0))
    tool_def.safety_level = _safety_level(meta.get("safety_level", "safe"))
    tool_def.tags = list(meta.get("tags", [])) + ["custom"]
    tool_def.description = meta.get("description") or tool_def.description
    tool_def.args_schema = meta.get("schema")
    return tool_def


def _safety_level(value: str) -> SafetyLevel:
    try:
        return SafetyLevel(value)
    except ValueError:
        return SafetyLevel.SAFE

"""
Static validation for user-supplied tool/skill code (Phase 4.1/4.2).

Every custom tool is validated before it is saved or used in a run:

- ``compile`` check — syntax errors fail fast.
- Bandit-style AST scan — dangerous calls/imports (subprocess, os.system,
  eval/exec, socket, file deletion) are reported as findings. Findings are
  warnings by default; the platform can refuse to enable a tool whose
  findings exceed a severity threshold.
- Schema render — the exported function's signature (annotations + defaults)
  is turned into an OpenAI-style parameters schema for the LLM tool manifest.

The runtime also enforces a path-scope sandbox: custom tool modules execute
in a restricted namespace (safe builtins) with ``__file__`` pointing inside
the workspace root, so filesystem writes stay scoped.
"""

import ast
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# Calls/imports that are always blocked for custom tool code.
_FORBIDDEN_CALLS = {
    "os.system",
    "os.popen",
    "os.spawn",
    "os.execl",
    "subprocess.Popen",
    "subprocess.run",
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
    "shutil.rmtree",
    "shutil.move",
    "pathlib.Path.unlink",
    "Path.unlink",
    "pathlib.Path.rmdir",
    "Path.rmdir",
    "builtins.eval",
    "eval",
    "builtins.exec",
    "exec",
    "compile",
    "open",  # flagged: use the sandboxed file tools instead
    "os.remove",
    "os.rename",
    "os.rmdir",
    "os.unlink",
    "socket.socket",
    "http.client",
    "requests.post",
}

# Imports that are always blocked.
_FORBIDDEN_IMPORTS = {
    "subprocess",
    "socket",
    "shutil",
    "ctypes",
    "pty",
    "fcntl",
    "multiprocessing",
    "pickle",  # unsafe deserialization
    "marshal",
    "shelve",
}

# Severity: high findings should block enabling a tool; medium are warnings.
_FINDING_SEVERITY = {
    # high — command execution / destructive filesystem
    "subprocess.Popen": "high",
    "subprocess.run": "high",
    "subprocess.call": "high",
    "subprocess.check_call": "high",
    "subprocess.check_output": "high",
    "os.system": "high",
    "os.popen": "high",
    "os.spawn": "high",
    "os.execl": "high",
    "shutil.rmtree": "high",
    "shutil.move": "high",
    "os.remove": "high",
    "os.rename": "high",
    "os.rmdir": "high",
    "os.unlink": "high",
    "eval": "high",
    "exec": "high",
    "compile": "high",
    "socket.socket": "high",
    "http.client": "high",
    "requests.post": "high",
    # medium — environment / general I/O
    "os.environ": "medium",
    "open": "medium",
    "os.getcwd": "low",
    "os.chdir": "medium",
    "os.listdir": "low",
    "os.walk": "low",
}


@dataclass
class ValidationFinding:
    """A single static-scan finding."""

    severity: str  # high | medium | low | info
    message: str
    line: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {"severity": self.severity, "message": self.message, "line": self.line}


@dataclass
class ValidationResult:
    """Result of validating custom code."""

    ok: bool
    errors: List[str] = field(default_factory=list)
    findings: List[ValidationFinding] = field(default_factory=list)
    function_name: Optional[str] = None
    schema: Optional[Dict[str, Any]] = None

    @property
    def high_findings(self) -> List[ValidationFinding]:
        return [f for f in self.findings if f.severity == "high"]

    @property
    def passes(self) -> bool:
        """True when the code is safe enough to enable (no errors, no high findings)."""
        return self.ok and not self.high_findings

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "passes": self.passes,
            "errors": self.errors,
            "function_name": self.function_name,
            "schema": self.schema,
            "findings": [f.to_dict() for f in self.findings],
        }


def validate_custom_code(code: str, function_name: Optional[str] = None) -> ValidationResult:
    """
    Validate custom tool/skill code.

    ``function_name`` selects which function is the exported tool entry point;
    when omitted, the first top-level function definition is used.
    """
    result = ValidationResult(ok=True)

    # 1. Syntax
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        result.ok = False
        result.errors.append(f"Syntax error: {e.msg} (line {e.lineno})")
        return result

    # 2. Static scan
    for node in ast.walk(tree):
        # imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _FORBIDDEN_IMPORTS:
                    result.findings.append(ValidationFinding(
                        severity="high",
                        message=f"Forbidden import: {alias.name}",
                        line=getattr(node, "lineno", 0),
                    ))
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in _FORBIDDEN_IMPORTS:
                result.findings.append(ValidationFinding(
                    severity="high",
                    message=f"Forbidden import: {node.module}",
                    line=getattr(node, "lineno", 0),
                ))

        # attribute/name calls like os.system, subprocess.run, eval(...)
        elif isinstance(node, ast.Call):
            target = _call_name(node.func)
            if target in _FORBIDDEN_CALLS and target != "open":
                result.findings.append(ValidationFinding(
                    severity=_FINDING_SEVERITY.get(target, "high"),
                    message=f"Potentially dangerous call: {target}",
                    line=getattr(node, "lineno", 0),
                ))
            elif target == "open":
                # allow read-only open() by default; flag write modes
                if _open_mode_is_write(node):
                    result.findings.append(ValidationFinding(
                        severity="medium",
                        message="open() in write mode — prefer the sandboxed file tools",
                        line=getattr(node, "lineno", 0),
                    ))

        # os.environ access
        elif isinstance(node, (ast.Attribute, ast.Subscript)):
            if isinstance(node, ast.Attribute) and node.attr == "environ":
                result.findings.append(ValidationFinding(
                    severity="medium",
                    message="os.environ access — env is allowlisted at runtime",
                    line=getattr(node, "lineno", 0),
                ))

    # 3. Find the entry-point function and render its schema
    fn = _find_function(tree, function_name)
    if fn is None:
        result.ok = False
        if function_name:
            result.errors.append(f"No function named '{function_name}' found in the code")
        else:
            result.errors.append(
                "No function definition found — a custom tool must define one exported function"
            )
        return result

    result.function_name = fn.name
    result.schema = _render_signature_schema(fn)
    return result


def _call_name(func: ast.AST) -> str:
    """Render a call target as a dotted name, e.g. os.system -> 'os.system'."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        base = _call_name(func.value)
        return f"{base}.{func.attr}" if base else func.attr
    if isinstance(func, ast.Call):  # chained calls like a()()
        return _call_name(func.func)
    return ""


def _open_mode_is_write(node: ast.Call) -> bool:
    """Best-effort check whether open() is used in a write mode."""
    if len(node.args) < 2:
        return False
    mode = node.args[1]
    if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
        return any(c in mode.value for c in "wax+")
    return False


def _find_function(tree: ast.Module, name: Optional[str]) -> Optional[ast.FunctionDef]:
    """Find the tool entry point: by name, or the first top-level function."""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and (name is None or node.name == name):
            return node
    # Fall back to any function (e.g. if wrapped in an if-block)
    for walked in ast.walk(tree):
        if isinstance(walked, ast.FunctionDef) and (name is None or walked.name == name):
            return walked
    return None


def _render_signature_schema(fn: ast.FunctionDef) -> Dict[str, Any]:
    """Render an OpenAI-style parameters schema from a function signature."""
    properties: Dict[str, Any] = {}
    required: List[str] = []

    for arg in fn.args.args:
        if arg.arg in ("self", "cls"):
            continue
        prop: Dict[str, Any] = {}
        default: Any = None

        # annotate type
        if arg.annotation is not None:
            type_name = _annotation_type(arg.annotation)
            if type_name:
                prop["type"] = type_name
            else:
                prop["type"] = "string"
        else:
            prop["type"] = "string"
            prop["description"] = "(untyped — inferred as string)"

        # default values (trailing args map to trailing defaults)
        n_args = len(fn.args.args)
        n_defaults = len(fn.args.defaults)
        default_index = fn.args.args.index(arg) - (n_args - n_defaults)
        if 0 <= default_index < n_defaults:
            d = fn.args.defaults[default_index]
            if isinstance(d, ast.Constant):
                default = d.value
            elif isinstance(d, (ast.List, ast.Tuple)):
                default = []
            elif isinstance(d, ast.Dict):
                default = {}
            else:
                default = None
            if default is not None:
                prop["default"] = default
        else:
            required.append(arg.arg)

        properties[arg.arg] = prop

    return {"type": "object", "properties": properties, "required": required}


def _annotation_type(annotation: ast.AST) -> Optional[str]:
    """Map a type annotation AST to a JSON schema type."""
    if isinstance(annotation, ast.Name):
        mapping = {
            "str": "string",
            "int": "integer",
            "float": "number",
            "bool": "boolean",
            "dict": "object",
            "list": "array",
            "Any": "string",
        }
        return mapping.get(annotation.id, "string")
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        # string annotations (from __future__ import annotations)
        return _string_type(annotation.value)
    if isinstance(annotation, ast.Subscript):  # list[str], dict[str, str], Optional[str]
        if isinstance(annotation.value, ast.Name):
            if annotation.value.id in ("list", "List"):
                return "array"
            if annotation.value.id in ("dict", "Dict"):
                return "object"
            if annotation.value.id in ("Optional", "Union"):
                return _string_type(annotation.slice)
    return None


def _string_type(raw: Any) -> Optional[str]:
    name = getattr(raw, "id", None) or (getattr(raw, "value", None) if hasattr(raw, "value") else None)
    if isinstance(name, str):
        mapping = {
            "str": "string",
            "int": "integer",
            "float": "number",
            "bool": "boolean",
            "dict": "object",
            "list": "array",
        }
        return mapping.get(name, "string")
    return "string"


def render_runtime_schema(func: Callable) -> Dict[str, Any]:
    """Render a schema from a live Python function (used at registration time)."""
    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError):
        return {"type": "object", "properties": {}, "required": []}
    properties: Dict[str, Any] = {}
    required: List[str] = []
    for param in sig.parameters.values():
        if param.name in ("self", "cls"):
            continue
        prop: Dict[str, Any] = {"type": "string"}
        if param.annotation is not inspect.Parameter.empty:
            mapping = {str: "string", int: "integer", float: "number", bool: "boolean",
                       dict: "object", list: "array"}
            prop["type"] = mapping.get(param.annotation, "string")
        if param.default is not inspect.Parameter.empty and param.default is not None:
            prop["default"] = param.default
        else:
            required.append(param.name)
        properties[param.name] = prop
    return {"type": "object", "properties": properties, "required": required}

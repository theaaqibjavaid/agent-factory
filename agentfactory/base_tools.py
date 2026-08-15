"""
Base Tools — Pluggable tool registry using decorator pattern.

Any domain-specific tool can be registered here and assigned to agents
via configuration files. Built-in tools ship in tools/ directory.

Usage:
    @tool("my_custom_tool", category="custom")
    def my_custom_tool(arg: str) -> str:
        '''Does something useful.'''
        return result
"""

import functools
import inspect
import os
import subprocess
import asyncio
from typing import Callable, Dict, Any, List, Optional, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum
from pydantic import BaseModel

if TYPE_CHECKING:
    from langchain_core.tools import Tool


class SafetyLevel(str, Enum):
    """Safety classification for tools."""
    SAFE = "safe"          # No risk, read-only
    MODIFIED = "modified"  # Writes files but safe
    DESTRUCTIVE = "destructive"  # Could cause data loss


@dataclass
class ToolDef:
    """Definition of a registered tool with metadata."""
    name: str
    func: Callable
    description: str
    args_schema: Optional[Dict[str, Any]] = None
    category: str = "generic"
    cost_per_call_usd: float = 0.0
    safety_level: SafetyLevel = SafetyLevel.SAFE
    tags: List[str] = field(default_factory=list)


@dataclass
class ToolMetadata:
    """Metadata for a tool — used by MCP integration and tool listings."""
    name: str
    category: str = "generic"
    description: str = ""
    cost_per_call_usd: float = 0.0
    safety_level: SafetyLevel = SafetyLevel.SAFE
    tags: List[str] = field(default_factory=list)


class ToolCall(BaseModel):
    """A single tool invocation request."""
    name: str
    arguments: Dict[str, Any]
    id: str = ""
    result: Optional[str] = None


def tool(
    name_or_func: Optional[Callable] = None,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    category: str = "generic",
    cost_per_call_usd: float = 0.0,
    safety_level: SafetyLevel = SafetyLevel.SAFE,
    tags: Optional[List[str]] = None,
):
    """
    Decorator to register a function as a tool.

    Usage:
        @tool("parse_pdf", category="document", tags=["parsing", "pdf"])
        def parse_pdf(file_path: str) -> str:
            ...

        OR without name:

        @tool(category="document")
        def parse_pdf(file_path: str) -> str:
            ...
    """
    # Handle positional name argument
    if isinstance(name_or_func, str):
        name = name_or_func
        name_or_func = None

    if name_or_func is None:
        def decorator(f: Callable) -> Callable:
            _register_tool(
                f,
                name=name,
                description=description,
                category=category,
                cost_per_call_usd=cost_per_call_usd,
                safety_level=safety_level,
                tags=tags or [],
            )
            return f
        return decorator

    # Called directly as @tool without arguments
    _register_tool(
        name_or_func,
        name=name,
        description=description,
        category=category,
        cost_per_call_usd=cost_per_call_usd,
        safety_level=safety_level,
        tags=tags or [],
    )
    return name_or_func


# Global tool registry
_TOOL_REGISTRY: Dict[str, ToolDef] = {}


def _register_tool(
    func: Callable,
    name: Optional[str],
    description: Optional[str],
    category: str,
    cost_per_call_usd: float,
    safety_level: SafetyLevel,
    tags: List[str],
) -> None:
    """Internal: Register a tool in the registry (idempotent)."""
    tool_name = name or func.__name__
    if tool_name in _TOOL_REGISTRY:
        # Already registered — skip to avoid duplicates on re-import
        return
    doc = description or inspect.getdoc(func) or func.__name__
    sig = inspect.signature(func)

    args_schema: Dict[str, Any] = {"properties": {}, "required": []}
    for param_name, param in sig.parameters.items():
        param_info: Dict[str, Any] = {"description": f"Parameter: {param_name}"}

        if param.annotation is str:
            param_info["type"] = "string"
        elif param.annotation is int:
            param_info["type"] = "integer"
        elif param.annotation is bool:
            param_info["type"] = "boolean"
        elif param.annotation is float:
            param_info["type"] = "number"
        else:
            param_info["type"] = "string"

        if param.default is not inspect.Parameter.empty:
            param_info["default"] = param.default
        else:
            args_schema["required"].append(param_name)

        args_schema["properties"][param_name] = param_info

    _TOOL_REGISTRY[tool_name] = ToolDef(
        name=tool_name,
        func=func,
        description=doc,
        args_schema=args_schema if args_schema["properties"] else None,
        category=category,
        cost_per_call_usd=cost_per_call_usd,
        safety_level=safety_level,
        tags=tags,
    )

    # Store metadata on the function for ToolRegistry.register_function
    func._tool_metadata = {
        "name": tool_name,
        "description": doc,
        "category": category,
        "cost_per_call_usd": cost_per_call_usd,
        "safety_level": safety_level,
        "tags": tags,
        "args_schema": args_schema if args_schema["properties"] else None,
    }


def register_tool(tool_def: ToolDef) -> None:
    """Manually register a pre-built ToolDef."""
    _TOOL_REGISTRY[tool_def.name] = tool_def


def get_tool(name: str) -> ToolDef:
    """Retrieve a registered tool by name."""
    if name not in _TOOL_REGISTRY:
        raise KeyError(
            f"Tool '{name}' not registered. Available: {list(_TOOL_REGISTRY.keys())}"
        )
    return _TOOL_REGISTRY[name]


def get_tools_by_category(category: str) -> List[ToolDef]:
    """Get all tools in a category."""
    return [t for t in _TOOL_REGISTRY.values() if t.category == category]


def get_tools_by_tag(tag: str) -> List[ToolDef]:
    """Get all tools with a specific tag."""
    return [t for t in _TOOL_REGISTRY.values() if tag in t.tags]


def list_tools() -> List[str]:
    """List all registered tool names."""
    return list(_TOOL_REGISTRY.keys())


def list_tools_detailed() -> List[Dict[str, Any]]:
    """List all tools with metadata."""
    return [
        {
            "name": t.name,
            "category": t.category,
            "cost_per_call_usd": t.cost_per_call_usd,
            "safety_level": t.safety_level.value,
            "tags": t.tags,
            "description": t.description[:80],
        }
        for t in _TOOL_REGISTRY.values()
    ]


def to_langchain_tools(tool_names: List[str]) -> List[Any]:
    """Convert registered tool names to LangChain Tool objects."""
    from langchain_core.tools import Tool
    tools = []
    for name in tool_names:
        try:
            tool_def = get_tool(name)
            tools.append(Tool(
                name=tool_def.name,
                description=tool_def.description,
                func=tool_def.func,
            ))
        except KeyError:
            continue
    return tools


def clear_registry() -> None:
    """Clear the tool registry (mainly for testing)."""
    _TOOL_REGISTRY.clear()


# ============================================================
# ToolRegistry: Class-based registry with async support
# ============================================================

class ToolWrapper:
    """Wraps a ToolDef to support async execution and metadata access."""

    def __init__(self, tool_def: ToolDef):
        self.metadata = ToolMetadata(
            name=tool_def.name,
            category=tool_def.category,
            description=tool_def.description,
            cost_per_call_usd=tool_def.cost_per_call_usd,
            safety_level=tool_def.safety_level,
            tags=tool_def.tags,
        )
        self._tool_def = tool_def
        self._func = tool_def.func
        self.signature = {"properties": tool_def.args_schema or {"properties": {}, "required": []}}

    async def execute(self, arguments: Dict[str, Any]) -> str:
        """Execute the tool with given arguments."""
        sig = inspect.signature(self._func)
        filtered_args = {}
        for param_name in sig.parameters:
            if param_name in arguments:
                filtered_args[param_name] = arguments[param_name]

        result = self._func(**filtered_args)

        # Handle async functions
        if inspect.isawaitable(result):
            result = await result

        return str(result)


class ToolRegistry:
    """Class-based tool registry that can be shared across agents."""

    def __init__(self):
        self._tools: Dict[str, ToolWrapper] = {}

    def register_function(self, func: Callable) -> None:
        """Register a function decorated with @tool."""
        if not hasattr(func, "_tool_metadata"):
            # Not a tool-decorated function — wrap it
            name = func.__name__
            tool_def = ToolDef(
                name=name,
                func=func,
                description=inspect.getdoc(func) or name,
                args_schema=None,
                category="generic",
                cost_per_call_usd=0.0,
                safety_level=SafetyLevel.SAFE,
                tags=[],
            )
        else:
            meta = func._tool_metadata
            tool_def = ToolDef(
                name=meta.get("name", func.__name__),
                func=func,
                description=meta.get("description", inspect.getdoc(func) or func.__name__),
                args_schema=None,
                category=meta.get("category", "generic"),
                cost_per_call_usd=meta.get("cost_per_call_usd", 0.0),
                safety_level=meta.get("safety_level", SafetyLevel.SAFE),
                tags=meta.get("tags", []),
            )

        self._tools[tool_def.name] = ToolWrapper(tool_def)

    def register_mcp_tool(self, name: str, metadata: ToolMetadata, server_name: str, client: Any) -> None:
        """Register a tool from an MCP server."""
        tool_def = ToolDef(
            name=name,
            func=lambda **kwargs: _mcp_tool_call(client, name, kwargs),
            description=metadata.description,
            args_schema={"properties": metadata.__dict__},  # Simplified
            category=f"mcp-{server_name}",
            cost_per_call_usd=0.0,
            safety_level=metadata.safety_level,
            tags=["mcp", server_name],
        )
        self._tools[name] = ToolWrapper(tool_def)

    def get(self, name: str) -> Optional[ToolWrapper]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def list_tools_detailed(self) -> List[Dict[str, Any]]:
        """List all tools with metadata."""
        return [
            {
                "name": t.metadata.name,
                "category": t.metadata.category,
                "cost_per_call_usd": t.metadata.cost_per_call_usd,
                "safety_level": t.metadata.safety_level.value if isinstance(t.metadata.safety_level, SafetyLevel) else t.metadata.safety_level,
                "tags": t.metadata.tags,
                "description": t.metadata.description[:80],
            }
            for t in self._tools.values()
        ]

    def get_by_category(self, category: str) -> List[ToolWrapper]:
        """Get all tools in a category."""
        return [t for t in self._tools.values() if t.metadata.category == category]

    def get_by_tag(self, tag: str) -> List[ToolWrapper]:
        """Get all tools with a specific tag."""
        return [t for t in self._tools.values() if tag in t.metadata.tags]


def _mcp_tool_call(client: Any, name: str, kwargs: Dict[str, Any]) -> str:
    """Synchronous wrapper for MCP tool calls.

    Works both from synchronous code and from within an existing event loop.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is None:
        # No running loop — create one and run to completion
        return asyncio.run(client.call_tool(name, kwargs))
    else:
        # We're inside an event loop — schedule the coroutine on it
        # and return a result via a future. Since ToolWrapper.execute
        # is async, we instead raise to signal the caller should await.
        # However, the old API is sync, so we use asyncio.run_coroutine_threadsafe
        # which works when the loop is running in another thread.
        # As a fallback, create a new loop in a separate thread.
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = asyncio.run_coroutine_threadsafe(
                client.call_tool(name, kwargs), loop
            )
            return future.result()

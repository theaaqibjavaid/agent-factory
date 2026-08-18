"""Provider-neutral tool contracts and dependency-injected registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping

ToolCallable = Callable[..., Any] | Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class ToolResult:
    """Normalized tool execution result."""

    tool_name: str
    output: Any = None
    error: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Tool:
    """A project-defined callable exposed to an agent."""

    name: str
    description: str
    handler: ToolCallable
    input_schema: Mapping[str, Any] = field(default_factory=dict)
    output_schema: Mapping[str, Any] = field(default_factory=dict)
    permissions: frozenset[str] = frozenset()
    safety_level: str = "safe"

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Tool name must not be empty")


class ToolRegistry:
    """Explicit, instance-scoped tool registry.

    The registry is intentionally not global. Applications may create separate
    registries for agents, projects, tests, or tenants without cross-talk.
    """

    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: {name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

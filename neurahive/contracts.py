"""Provider-neutral execution contracts for NeuraHive v2.

These contracts intentionally contain no platform, Studio, database, or
provider-SDK dependencies. Implementations live in adapters or consuming
projects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class ModelRequest:
    """Normalized model-generation request."""

    messages: Sequence[Mapping[str, Any]]
    model_id: str | None = None
    tools: Sequence[Mapping[str, Any]] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelResponse:
    """Provider-neutral model response."""

    content: Any = None
    tool_calls: Sequence[Mapping[str, Any]] = ()
    usage: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VerificationResult:
    """Provider-neutral verification result."""

    passed: bool
    reason: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)


class Verifier(Protocol):
    """Contract for output/result verification."""

    async def verify(self, *, result: Any, context: Mapping[str, Any] | None = None) -> VerificationResult: ...


class ToolExecutor(Protocol):
    """Contract for executing a validated tool call."""

    async def execute(
        self,
        *,
        tool_name: str,
        arguments: Mapping[str, Any],
        metadata: Mapping[str, Any] | None = None,
    ) -> Any: ...


class MCPProvider(Protocol):
    """Contract for an MCP adapter; transport remains outside core."""

    async def list_tools(self) -> Sequence[Mapping[str, Any]]: ...

    async def call_tool(self, name: str, arguments: Mapping[str, Any]) -> Any: ...

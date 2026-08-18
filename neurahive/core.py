"""Dependency-injected agent contracts for NeuraHive v2.

This module deliberately has no imports from the legacy AgentFactory package,
FastAPI, databases, Studio, or provider SDKs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence

from neurahive.providers import MemoryProvider, ModelProvider
from neurahive.tools import ToolRegistry, ToolResult


class ExecutionError(RuntimeError):
    """Raised when an agent cannot complete an execution."""


@dataclass(frozen=True)
class AgentConfig:
    """Immutable, project-owned agent configuration."""

    name: str
    instructions: str = ""
    model: str | None = None
    max_iterations: int = 20
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Agent name must not be empty")
        if self.max_iterations < 1:
            raise ValueError("max_iterations must be >= 1")


@dataclass
class AgentContext:
    """Execution context supplied by the consumer or workflow engine."""

    task: str
    agent_id: str | None = None
    workflow_id: str | None = None
    task_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    previous_results: list[Any] = field(default_factory=list)


@dataclass(frozen=True)
class AgentResult:
    """Normalized result returned by the core runtime."""

    output: Any
    agent_name: str
    iterations: int = 1
    tool_calls: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)


class AgentExecutor(Protocol):
    """Optional execution strategy supplied by a provider/runtime adapter."""

    async def execute(
        self,
        *,
        agent: Agent,
        context: AgentContext,
    ) -> AgentResult: ...


@dataclass
class Agent:
    """A reusable agent definition with injected execution dependencies.

    The core does not discover dependencies from a database or global
    registries. The application constructs the agent with explicit providers.
    """

    config: AgentConfig
    model_provider: ModelProvider
    tools: ToolRegistry = field(default_factory=ToolRegistry)
    memory: MemoryProvider | None = None
    executor: AgentExecutor | None = None

    @property
    def name(self) -> str:
        return self.config.name

    async def run(self, task: str, *, context: AgentContext | None = None) -> AgentResult:
        """Execute the agent through its injected execution strategy."""
        run_context = context or AgentContext(task=task)
        if not run_context.task:
            raise ValueError("Agent task must not be empty")
        if self.executor is None:
            raise ExecutionError(
                "No AgentExecutor was injected. Provide a runtime/executor adapter."
            )
        return await self.executor.execute(agent=self, context=run_context)


class AgentRuntime:
    """Small runtime facade that executes an explicitly constructed agent."""

    def __init__(self, *, executor: AgentExecutor) -> None:
        self._executor = executor

    async def run(self, agent: Agent, task: str, *, context: AgentContext | None = None) -> AgentResult:
        run_context = context or AgentContext(task=task)
        return await self._executor.execute(agent=agent, context=run_context)

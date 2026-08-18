"""Translation boundary from legacy agent profiles to NeuraHive v2.

The adapter intentionally does not import the legacy runtime. It accepts the
legacy persona shape structurally and translates only configuration concerns.
Legacy persistence, MCP lifecycle, failover, verification, and retry behavior
remain outside the NeuraHive core until their dedicated v2 phases.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, Sequence

from neurahive import Agent, AgentConfig, AgentContext, AgentResult, InProcessRuntime, ToolRegistry


class LegacyAgentAdapter:
    """Compatibility wrapper around an explicitly constructed NeuraHive agent."""

    def __init__(self, runtime_agent: Agent):
        if not isinstance(runtime_agent, Agent):
            raise TypeError("runtime_agent must be a neurahive.Agent")
        self._runtime_agent = runtime_agent

    @classmethod
    def from_persona(
        cls,
        persona: Any,
        *,
        model_provider: Any,
        tools: ToolRegistry | None = None,
        memory: Any | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "LegacyAgentAdapter":
        """Translate a legacy ``AgentPersona``-shaped object into NeuraHive.

        The input is structural so this compatibility module does not force the
        NeuraHive package to import legacy Pydantic models.
        """
        name = getattr(persona, "name", None) or getattr(persona, "rank", "legacy-agent")
        instructions = getattr(persona, "system_instructions", "") or ""
        preferences = getattr(persona, "model_preferences", None) or getattr(persona, "model_preference", None) or []
        max_iterations = int(getattr(persona, "max_iterations", 20) or 20)
        responsibilities = list(getattr(persona, "responsibilities", []) or [])
        if not instructions and responsibilities:
            instructions = "Responsibilities: " + ", ".join(str(item) for item in responsibilities)

        config = AgentConfig(
            name=str(name),
            instructions=instructions,
            model=str(preferences[0]) if preferences else None,
            max_iterations=max_iterations,
            metadata={**(metadata or {}), "compatibility": "legacy-agent"},
        )
        return cls(
            Agent(
                config=config,
                model_provider=model_provider,
                tools=tools or ToolRegistry(),
                memory=memory,
            )
        )

    @property
    def runtime_agent(self) -> Agent:
        return self._runtime_agent

    async def run(
        self,
        task_description: str,
        initial_input: str | None = None,
        max_iterations: int | None = None,
        tools: list[str] | None = None,
    ) -> dict[str, Any]:
        """Expose the legacy result shape while using the v2 runtime."""
        agent = self._select_agent(max_iterations=max_iterations, tools=tools)
        task = task_description
        if initial_input:
            task = f"{task}\n\nInitial Input:\n{initial_input}"
        result = await InProcessRuntime().run(agent, task)
        return self._legacy_result(result)

    async def think(
        self,
        task: str,
        context: list[dict[str, Any]] | None = None,
        require_tool: bool = False,
    ) -> str:
        """Provide the legacy thinking surface using a single v2 model turn."""
        metadata = {"compatibility": "legacy-think", "require_tool": require_tool}
        if context:
            metadata["legacy_context"] = context
        result = await InProcessRuntime().run(
            self._runtime_agent,
            task,
            context=AgentContext(task=task, metadata=metadata),
        )
        return str(result.output)

    async def execute_tool(self, tool_name: str, tool_args: dict[str, Any]) -> str:
        """Execute a registered v2 tool through the compatibility boundary."""
        tool = self._runtime_agent.tools.get(tool_name)
        try:
            value = tool.handler(**tool_args)
            if hasattr(value, "__await__"):
                value = await value
            return str(value)
        except Exception as exc:  # compatibility surface preserves string errors
            return f"Error: Tool '{tool_name}' failed: {exc}"

    def _select_agent(self, *, max_iterations: int | None, tools: list[str] | None) -> Agent:
        config = self._runtime_agent.config
        if max_iterations is not None:
            config = replace(config, max_iterations=max(1, max_iterations))

        registry = self._runtime_agent.tools
        if tools is not None:
            registry = ToolRegistry([registry.get(name) for name in tools])

        return replace(self._runtime_agent, config=config, tools=registry)

    @staticmethod
    def _legacy_result(result: AgentResult) -> dict[str, Any]:
        return {
            "result": result.output,
            "stats": {
                "iterations": result.iterations,
                "tool_calls_made": result.tool_calls,
            },
            "verification_errors": [],
        }

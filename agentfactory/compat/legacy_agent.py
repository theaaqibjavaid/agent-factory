"""Legacy AgentFactory compatibility adapter.

This module deliberately keeps the legacy surface thin. New code should depend
on the runtime contracts rather than importing platform internals directly.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class LegacyAgentAdapter:
    """Adapt the legacy ``RunnableAgent`` surface to a runtime agent.

    The adapter owns no LLM, memory, MCP, or verification implementation. It
    forwards execution to the supplied runtime agent, keeping compatibility
    concerns at the boundary.
    """

    def __init__(self, runtime_agent: Any):
        if runtime_agent is None:
            raise ValueError("runtime_agent is required")
        self._runtime_agent = runtime_agent

    @property
    def runtime_agent(self) -> Any:
        """Return the wrapped runtime agent."""
        return self._runtime_agent

    async def run(
        self,
        task_description: str,
        initial_input: Optional[str] = None,
        max_iterations: Optional[int] = None,
        tools: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Preserve the legacy ``RunnableAgent.run`` contract."""
        return await self._runtime_agent.run(
            task_description=task_description,
            initial_input=initial_input,
            max_iterations=max_iterations,
            tools=tools,
        )

    async def think(
        self,
        task: str,
        context: Optional[List[Dict[str, Any]]] = None,
        require_tool: bool = False,
    ) -> str:
        """Preserve the legacy ``RunnableAgent.think`` contract."""
        return await self._runtime_agent.think(
            task=task,
            context=context,
            require_tool=require_tool,
        )

    async def execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> str:
        """Preserve the legacy single-tool execution surface."""
        return await self._runtime_agent.execute_tool(tool_name, tool_args)

    def __getattr__(self, name: str) -> Any:
        """Forward read-only/rare legacy attributes without duplicating state."""
        return getattr(self._runtime_agent, name)

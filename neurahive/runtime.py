"""Platform-independent execution runtime for NeuraHive v2.

This runtime intentionally performs one model turn. Native tool-call loops,
policy decisions, retries, approvals, and durable execution are introduced in
later phases. The important Phase 1 property is that execution is entirely
constructed from injected public contracts.
"""

from __future__ import annotations

from typing import Any

from neurahive.contracts import ModelResponse
from neurahive.core import Agent, AgentContext, AgentExecutor, AgentResult


class BasicAgentExecutor(AgentExecutor):
    """Minimal provider-neutral executor suitable for SDK consumers and tests."""

    async def execute(self, *, agent: Agent, context: AgentContext) -> AgentResult:
        model = agent.model_provider.get_model(agent.config.model)
        messages: list[dict[str, Any]] = []
        if agent.config.instructions:
            messages.append({"role": "system", "content": agent.config.instructions})
        messages.append({"role": "user", "content": context.task})

        response = await agent.model_provider.generate(
            model=model,
            messages=messages,
            tools=self._tool_schemas(agent),
            metadata={
                "agent_name": agent.name,
                "agent_id": context.agent_id,
                "workflow_id": context.workflow_id,
                "task_id": context.task_id,
            },
        )

        if isinstance(response, ModelResponse):
            return AgentResult(
                output=response.content,
                agent_name=agent.name,
                iterations=1,
                tool_calls=len(response.tool_calls),
                metadata=response.metadata,
            )

        return AgentResult(output=response, agent_name=agent.name)

    @staticmethod
    def _tool_schemas(agent: Agent) -> list[dict[str, Any]]:
        """Expose tool metadata without executing tools.

        Actual structured tool execution is deliberately a Phase 4 concern.
        """
        return [
            {
                "name": name,
                "description": agent.tools.get(name).description,
                "input_schema": dict(agent.tools.get(name).input_schema),
            }
            for name in agent.tools.names()
        ]


class InProcessRuntime:
    """Convenience runtime that binds ``BasicAgentExecutor`` to an agent."""

    def __init__(self) -> None:
        self.executor = BasicAgentExecutor()

    async def run(self, agent: Agent, task: str, *, context: AgentContext | None = None) -> AgentResult:
        return await self.executor.execute(
            agent=agent,
            context=context or AgentContext(task=task),
        )

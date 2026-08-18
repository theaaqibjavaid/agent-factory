"""Compatibility-boundary tests for the legacy RunnableAgent surface."""

import asyncio
from unittest.mock import AsyncMock

from agentfactory.compat import LegacyAgentAdapter


class TestLegacyAgentAdapter:
    def test_run_forwards_legacy_arguments(self):
        runtime = AsyncMock()
        runtime.run.return_value = {"result": "ok"}
        adapter = LegacyAgentAdapter(runtime)

        result = asyncio.run(
            adapter.run(
                "do work",
                initial_input="context",
                max_iterations=3,
                tools=["git"],
            )
        )

        assert result == {"result": "ok"}
        runtime.run.assert_awaited_once_with(
            task_description="do work",
            initial_input="context",
            max_iterations=3,
            tools=["git"],
        )

    def test_think_forwards_legacy_arguments(self):
        runtime = AsyncMock()
        runtime.think.return_value = "answer"
        adapter = LegacyAgentAdapter(runtime)

        result = asyncio.run(
            adapter.think("question", context=[{"role": "user", "content": "x"}], require_tool=True)
        )

        assert result == "answer"
        runtime.think.assert_awaited_once_with(
            task="question",
            context=[{"role": "user", "content": "x"}],
            require_tool=True,
        )

    def test_execute_tool_forwards_arguments(self):
        runtime = AsyncMock()
        runtime.execute_tool.return_value = "tool result"
        adapter = LegacyAgentAdapter(runtime)

        result = asyncio.run(adapter.execute_tool("read_file", {"path": "x"}))

        assert result == "tool result"
        runtime.execute_tool.assert_awaited_once_with("read_file", {"path": "x"})

    def test_attributes_are_read_through(self):
        runtime = type("Runtime", (), {"stats": {"iterations": 1}})()
        adapter = LegacyAgentAdapter(runtime)
        assert adapter.stats == {"iterations": 1}

    def test_runtime_agent_is_required(self):
        try:
            LegacyAgentAdapter(None)
            assert False, "Expected ValueError"
        except ValueError as exc:
            assert str(exc) == "runtime_agent is required"

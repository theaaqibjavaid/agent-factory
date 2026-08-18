"""Tests for the legacy-to-NeuraHive translation boundary."""

from __future__ import annotations

import pytest

from agentfactory.compat import LegacyAgentAdapter
from neurahive import Model, ModelResponse, Tool, ToolRegistry


class FakeProvider:
    def get_model(self, model_id=None):
        return Model(provider="fake", model_id=model_id or "fake")

    async def generate(self, *, model, messages, tools=(), **kwargs):
        return ModelResponse(content=f"handled: {messages[-1]['content']}")


class LegacyPersona:
    rank = "Senior"
    responsibilities = ["research", "write"]
    system_instructions = "Be precise."
    model_preferences = ["fake-model"]
    max_iterations = 7


@pytest.mark.asyncio
async def test_persona_is_translated_without_importing_legacy_models():
    adapter = LegacyAgentAdapter.from_persona(
        LegacyPersona(),
        model_provider=FakeProvider(),
    )

    assert adapter.runtime_agent.config.name == "Senior"
    assert adapter.runtime_agent.config.instructions == "Be precise."
    assert adapter.runtime_agent.config.model == "fake-model"
    assert adapter.runtime_agent.config.max_iterations == 7

    result = await adapter.run("hello", initial_input="world")
    assert result["result"] == "handled: hello\n\nInitial Input:\nworld"
    assert result["stats"]["iterations"] == 1


@pytest.mark.asyncio
async def test_legacy_tool_execution_uses_instance_scoped_v2_registry():
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="echo",
            description="Echo text",
            handler=lambda text: text,
        )
    )
    adapter = LegacyAgentAdapter.from_persona(
        LegacyPersona(),
        model_provider=FakeProvider(),
        tools=registry,
    )

    assert await adapter.execute_tool("echo", {"text": "ok"}) == "ok"


@pytest.mark.asyncio
async def test_legacy_tool_filter_isolated_from_original_registry():
    registry = ToolRegistry()
    registry.register(Tool(name="a", description="a", handler=lambda: "a"))
    registry.register(Tool(name="b", description="b", handler=lambda: "b"))
    adapter = LegacyAgentAdapter.from_persona(
        LegacyPersona(),
        model_provider=FakeProvider(),
        tools=registry,
    )

    result = await adapter.run("hello", tools=["a"])
    assert result["result"] == "handled: hello"
    assert "b" in registry

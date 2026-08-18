"""Independent NeuraHive runtime tests.

These tests intentionally use a fake model provider and no AgentFactory,
FastAPI, database, or provider SDK dependency.
"""

from __future__ import annotations

import pytest

from neurahive import (
    Agent,
    AgentConfig,
    InProcessRuntime,
    Model,
    ModelResponse,
    ModelProvider,
    Tool,
    ToolRegistry,
)


class FakeModelProvider:
    def get_model(self, model_id: str | None = None) -> Model:
        return Model(provider="fake", model_id=model_id or "fake-model")

    async def generate(self, *, model, messages, tools=(), **kwargs):
        assert messages[-1]["role"] == "user"
        return ModelResponse(
            content=f"handled: {messages[-1]['content']}",
            metadata={"provider": model.provider},
        )


@pytest.mark.asyncio
async def test_external_style_agent_executes_without_legacy_runtime() -> None:
    agent = Agent(
        config=AgentConfig(
            name="example-agent",
            instructions="Answer clearly.",
            model="fake-model",
        ),
        model_provider=FakeModelProvider(),
        tools=ToolRegistry(),
    )

    result = await InProcessRuntime().run(agent, "hello")

    assert result.output == "handled: hello"
    assert result.agent_name == "example-agent"
    assert result.metadata["provider"] == "fake"


def test_tool_registry_is_instance_scoped() -> None:
    first = ToolRegistry()
    second = ToolRegistry()

    first.register(
        Tool(
            name="first-only",
            description="test",
            handler=lambda: "ok",
        )
    )

    assert "first-only" in first
    assert "first-only" not in second

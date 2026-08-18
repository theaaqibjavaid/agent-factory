from __future__ import annotations

import pytest

from neurahive import Agent, AgentConfig, InProcessRuntime, Model, ModelResponse


class ConsumerOwnedProvider:
    def get_model(self, model_id: str | None = None) -> Model:
        return Model(provider="consumer", model_id=model_id or "demo")

    async def generate(self, *, model, messages, tools=(), **kwargs):
        return ModelResponse(content=f"consumer:{messages[-1]['content']}")


@pytest.mark.asyncio
async def test_unrelated_consumer_uses_only_public_neurahive_api() -> None:
    agent = Agent(
        config=AgentConfig(name="consumer", model="demo"),
        model_provider=ConsumerOwnedProvider(),
    )

    result = await InProcessRuntime().run(agent, "hello")

    assert result.output == "consumer:hello"
    assert result.agent_name == "consumer"

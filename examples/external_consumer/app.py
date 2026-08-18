from __future__ import annotations

import asyncio

from neurahive import Agent, AgentConfig, InProcessRuntime, Model, ModelResponse


class ConsumerModelProvider:
    """Example provider owned entirely by the consuming application."""

    def get_model(self, model_id: str | None = None) -> Model:
        return Model(provider="consumer-example", model_id=model_id or "demo")

    async def generate(self, *, model, messages, tools=(), **kwargs):
        return ModelResponse(
            content=f"handled: {messages[-1]['content']}",
            metadata={"provider": model.provider},
        )


async def main() -> None:
    agent = Agent(
        config=AgentConfig(
            name="consumer-agent",
            instructions="Answer clearly.",
            model="demo",
        ),
        model_provider=ConsumerModelProvider(),
    )

    result = await InProcessRuntime().run(
        agent,
        "hello from an unrelated project",
    )
    print(result.output)


if __name__ == "__main__":
    asyncio.run(main())

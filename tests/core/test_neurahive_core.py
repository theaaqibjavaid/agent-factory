"""Contract tests for the dependency-injected NeuraHive v2 core."""

from neurahive import Agent, AgentConfig, AgentContext, Tool, ToolRegistry


class StubModelProvider:
    def get_model(self, model_id=None):
        return {"model_id": model_id or "stub"}


class StubExecutor:
    async def execute(self, *, agent, context):
        from neurahive import AgentResult

        return AgentResult(output=context.task.upper(), agent_name=agent.name)


def test_core_imports_without_platform_modules():
    import sys

    assert "agentfactory.app" not in sys.modules
    assert "fastapi" not in sys.modules


def test_agent_is_constructed_with_explicit_dependencies():
    registry = ToolRegistry(
        [Tool(name="echo", description="Echo", handler=lambda value: value)]
    )
    agent = Agent(
        config=AgentConfig(name="test-agent", instructions="Test"),
        model_provider=StubModelProvider(),
        tools=registry,
        executor=StubExecutor(),
    )

    assert agent.name == "test-agent"
    assert registry.names() == ("echo",)


async def test_agent_runtime_does_not_discover_dependencies():
    agent = Agent(
        config=AgentConfig(name="test-agent"),
        model_provider=StubModelProvider(),
        executor=StubExecutor(),
    )

    result = await agent.run("hello")

    assert result.output == "HELLO"
    assert result.agent_name == "test-agent"


def test_context_is_project_owned_data():
    context = AgentContext(task="work", workflow_id="wf-1")
    assert context.task == "work"
    assert context.workflow_id == "wf-1"

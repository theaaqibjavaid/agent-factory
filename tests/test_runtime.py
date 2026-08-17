"""
Phase 2 runtime unit tests (agentfactory.runtime).

Uses a scripted fake LLM so no API keys are needed:

- final-answer run (token event, completed result, cost stats)
- tool-call run (tool_call/tool_result events, tool actually executed)
- DESTRUCTIVE safety gate: blocked by default, allowed with workspace toggle
- max_iterations cap, verification event, memory persistence
- render_agent_config (Phase 2.1): system prompt + tool manifest
"""

import json

import pytest

from agentfactory.base_tools import SafetyLevel, ToolDef, register_tool, _TOOL_REGISTRY
from agentfactory.memory import PersistentMemory
from agentfactory.runtime import (
    PlatformAgentRuntime,
    RunEventBroker,
    build_system_prompt,
    render_agent_config,
)


def _agent_row(tools=None, hitl_mode="auto", max_iterations=20, name="Tester"):
    return {
        "id": "agent-1",
        "name": name,
        "rank": "Junior",
        "role_description": "Runs tests",
        "system_instructions": "You are a test agent.",
        "model_preferences": json.dumps(["gemini-2.5-flash"]),
        "tools": json.dumps(tools or []),
        "skills": "[]",
        "mcp_servers": "[]",
        "temperature": 0.2,
        "max_budget_usd_per_day": 5.0,
        "hitl_mode": hitl_mode,
        "max_iterations": max_iterations,
    }


def _fake_llm(responses):
    """Scripted LLM: returns responses in order, repeating the last one."""
    state = {"n": 0}

    async def fake(messages, tools):
        idx = min(state["n"], len(responses) - 1)
        state["n"] += 1
        return responses[idx]

    return fake


def _collect_events(broker):
    return broker.events


@pytest.fixture
def echo_tool():
    """Register a harmless SAFE tool for the test agent, then clean up."""
    name = "runtime_test_echo"

    def echo(text: str) -> str:
        return f"echo:{text}"

    register_tool(ToolDef(
        name=name, func=echo, description="Echoes text",
        args_schema={"properties": {"text": {"type": "string"}}, "required": ["text"]},
        safety_level=SafetyLevel.SAFE, cost_per_call_usd=0.01,
    ))
    yield name
    _TOOL_REGISTRY.pop(name, None)


@pytest.fixture
def destructive_tool():
    name = "runtime_test_destructive"

    def nuke(path: str) -> str:
        return "destroyed"

    register_tool(ToolDef(
        name=name, func=nuke, description="Deletes everything",
        args_schema={"properties": {"path": {"type": "string"}}, "required": ["path"]},
        safety_level=SafetyLevel.DESTRUCTIVE,
    ))
    yield name
    _TOOL_REGISTRY.pop(name, None)


class TestRenderConfig:
    def test_render_agent_config(self, echo_tool):
        row = _agent_row(tools=[echo_tool])
        rendered = render_agent_config(row)
        assert rendered["name"] == "Tester"
        assert "You are a test agent." in rendered["system_prompt"]
        assert echo_tool in rendered["system_prompt"]
        assert len(rendered["tools"]) == 1
        assert rendered["tools"][0]["name"] == echo_tool
        assert rendered["tools"][0]["safety"] == "safe"
        assert rendered["hitl_mode"] == "auto"

    def test_render_skips_unknown_tools(self):
        row = _agent_row(tools=["definitely_not_a_real_tool_xyz"])
        rendered = render_agent_config(row)
        assert rendered["tools"] == []

    def test_build_system_prompt_mentions_tools(self, echo_tool):
        row = _agent_row(tools=[echo_tool])
        prompt = build_system_prompt(row, render_agent_config(row)["tools"])
        assert "Available tools" in prompt
        assert echo_tool in prompt


class TestRuntimeRun:
    @pytest.mark.asyncio
    async def test_final_answer_run(self, echo_tool):
        broker = RunEventBroker()
        runtime = PlatformAgentRuntime(
            _agent_row(tools=[echo_tool]),
            llm_generate=_fake_llm([{"text": "Hello, world!", "tool_calls": []}]),
        )
        result = await runtime.run("Say hi", "run-1", broker)
        events = _collect_events(broker)

        assert result["result"] == "Hello, world!"
        assert result["stats"]["iterations"] == 1
        names = [e["event"] for e in events]
        assert "run.start" in names
        assert "token" in names
        assert "cost" in names
        token = next(e for e in events if e["event"] == "token")
        assert token["data"]["content"] == "Hello, world!"

    @pytest.mark.asyncio
    async def test_tool_call_run(self, echo_tool):
        broker = RunEventBroker()
        fake = _fake_llm([
            {"text": "", "tool_calls": [{"name": echo_tool, "arguments": {"text": "ping"}, "id": "1"}]},
            {"text": "Done using the tool.", "tool_calls": []},
        ])
        runtime = PlatformAgentRuntime(_agent_row(tools=[echo_tool]), llm_generate=fake)
        result = await runtime.run("Use the tool", "run-2", broker)
        events = _collect_events(broker)

        assert result["result"] == "Done using the tool."
        assert result["stats"]["tool_calls_made"] == 1
        assert result["stats"]["total_cost_usd"] == pytest.approx(0.01)
        names = [e["event"] for e in events]
        assert "tool_call" in names and "tool_result" in names and "verify" in names
        tool_result = next(e for e in events if e["event"] == "tool_result")
        assert tool_result["data"]["result"] == "echo:ping"

    @pytest.mark.asyncio
    async def test_max_iterations_capped(self, echo_tool):
        """A model that always calls a tool must stop at max_iterations."""
        broker = RunEventBroker()
        fake = _fake_llm([{"text": "", "tool_calls": [{"name": echo_tool, "arguments": {"text": "x"}}]}])
        runtime = PlatformAgentRuntime(_agent_row(tools=[echo_tool], max_iterations=3), llm_generate=fake)
        result = await runtime.run("loop", "run-3", broker)
        assert result["stats"]["iterations"] == 3
        assert result["stats"]["tool_calls_made"] == 3

    @pytest.mark.asyncio
    async def test_verification_event_present(self, echo_tool):
        broker = RunEventBroker()
        runtime = PlatformAgentRuntime(
            _agent_row(tools=[echo_tool]),
            llm_generate=_fake_llm([{"text": "answer", "tool_calls": []}]),
        )
        await runtime.run("task", "run-4", broker)
        verify = [e for e in broker.events if e["event"] == "verify"]
        assert len(verify) == 1
        assert "summary" in verify[0]["data"]
        assert "passed" in verify[0]["data"]

    @pytest.mark.asyncio
    async def test_memory_saved_after_run(self, echo_tool, tmp_path, monkeypatch):
        monkeypatch.setenv("MEMORY_DB_PATH", str(tmp_path / "memory.db"))
        memory = PersistentMemory(agent_id="ws:agent-1")
        broker = RunEventBroker()
        runtime = PlatformAgentRuntime(
            _agent_row(tools=[echo_tool]),
            llm_generate=_fake_llm([{"text": "remembered", "tool_calls": []}]),
            memory=memory,
        )
        await runtime.run("task", "run-5", broker)
        history = memory.load_history()
        assert any("remembered" in m.get("content", "") for m in history)
        assert any(e["event"] == "memory" for e in broker.events)


class TestSafetyGate:
    @pytest.mark.asyncio
    async def test_destructive_blocked_by_default(self, destructive_tool):
        broker = RunEventBroker()
        fake = _fake_llm([
            {"text": "", "tool_calls": [{"name": destructive_tool, "arguments": {"path": "/"}}]},
            {"text": "finished", "tool_calls": []},
        ])
        runtime = PlatformAgentRuntime(
            _agent_row(tools=[destructive_tool]),
            llm_generate=fake,
        )
        result = await runtime.run("do it", "run-6", broker)

        tool_results = [e for e in broker.events if e["event"] == "tool_result"]
        assert "Blocked" in tool_results[0]["data"]["result"]
        assert "DESTRUCTIVE" in tool_results[0]["data"]["result"]
        errors = [e for e in broker.events if e["event"] == "error"]
        assert errors and "Blocked" in errors[0]["data"]["message"]

    @pytest.mark.asyncio
    async def test_destructive_allowed_with_workspace_toggle(self, destructive_tool):
        broker = RunEventBroker()
        fake = _fake_llm([
            {"text": "", "tool_calls": [{"name": destructive_tool, "arguments": {"path": "/tmp/x"}}]},
            {"text": "done", "tool_calls": []},
        ])
        runtime = PlatformAgentRuntime(
            _agent_row(tools=[destructive_tool]),
            workspace_settings={"allow_destructive": True},
            llm_generate=fake,
        )
        await runtime.run("do it", "run-7", broker)
        tool_results = [e for e in broker.events if e["event"] == "tool_result"]
        assert tool_results[0]["data"]["result"] == "destroyed"

"""
Regression tests for Phase 0 fixes in agentfactory.base_agent:

0.1 - RunnableAgent._mcp_clients is initialized (close()/_ensure_mcp_tools() no longer crash)
0.2 - AgentExecutionStats uses timezone-aware datetimes (no naive/aware TypeError)
0.4 - _save_persistent_history() persists only new messages (no quadratic DB growth)
"""

import asyncio
import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from agentfactory.base_agent import AgentExecutionStats, AgentPersona, RunnableAgent
from agentfactory.base_tools import ToolRegistry
from agentfactory.mcp_integration import MCPServerConfig
from agentfactory.memory import PersistentMemory


def make_agent(**kwargs) -> RunnableAgent:
    kwargs.setdefault("persona", AgentPersona(rank="Junior"))
    kwargs.setdefault("tool_registry", ToolRegistry())
    return RunnableAgent(**kwargs)


class TestMcpClientLifecycle:
    """Regression 0.1 — _mcp_clients must exist before any MCP usage."""

    def test_close_without_mcp_config(self):
        agent = make_agent()
        # Used to raise AttributeError: no attribute '_mcp_clients'
        asyncio.run(agent.close())

    def test_ensure_mcp_tools_with_config_does_not_crash(self):
        agent = make_agent(
            mcp_configs={"broken": MCPServerConfig(name="broken", command="definitely-not-a-real-cmd-xyz")}
        )
        # Connection fails and is logged; must NOT raise AttributeError
        asyncio.run(agent._ensure_mcp_tools())
        assert agent._mcp_clients == {}

    def test_close_after_ensure_mcp_tools(self):
        agent = make_agent(
            mcp_configs={"broken": MCPServerConfig(name="broken", command="definitely-not-a-real-cmd-xyz")}
        )
        asyncio.run(agent._ensure_mcp_tools())
        asyncio.run(agent.close())

    def test_mcp_clients_initialized_empty(self):
        agent = make_agent()
        assert agent._mcp_clients == {}


class TestExecutionStats:
    """Regression 0.2 — naive vs aware datetime comparison must never raise."""

    def test_duration_before_run_never_raises(self):
        stats = AgentExecutionStats()
        assert stats.duration_seconds >= 0

    def test_duration_after_run(self):
        stats = AgentExecutionStats()
        stats.start_time = datetime.now(timezone.utc)
        stats.end_time = datetime.now(timezone.utc)
        assert stats.duration_seconds >= 0

    def test_default_start_time_is_aware(self):
        stats = AgentExecutionStats()
        assert stats.start_time.tzinfo is not None

    def test_to_dict_includes_duration(self):
        stats = AgentExecutionStats()
        assert "duration_seconds" in stats.to_dict()


class TestPersistentHistory:
    """Regression 0.4 — only NEW messages may be written to the memory DB."""

    def _row_count(self, memory: PersistentMemory, agent_id: str) -> int:
        conn = memory._get_conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM memory_history WHERE agent_id = ?", (agent_id,)
            ).fetchone()
            return int(row["c"])
        finally:
            conn.close()

    async def test_two_turns_store_exactly_four_messages(self):
        tmp_db = tempfile.mktemp(suffix=".db")
        try:
            memory = PersistentMemory(agent_id="dup-regression", db_path=tmp_db)
            agent = make_agent(memory=memory)
            agent.llm_manager.generate_with_failover = AsyncMock(return_value="ok")

            await agent.think("first task")
            await agent.think("second task")

            # 2 turns x (user + assistant) = 4 rows. Before the fix this grew
            # quadratically (2 + 4 = 6 rows after two turns).
            assert self._row_count(memory, "dup-regression") == 4
        finally:
            if os.path.exists(tmp_db):
                os.unlink(tmp_db)

    async def test_history_loaded_from_db_is_not_resaved(self):
        tmp_db = tempfile.mktemp(suffix=".db")
        try:
            memory = PersistentMemory(agent_id="dup-load", db_path=tmp_db)
            memory.save_history(
                [{"role": "user", "content": "old"}, {"role": "assistant", "content": "old reply"}]
            )

            # A new agent instance loads the 2 persisted messages on init.
            agent = make_agent(memory=memory)
            assert len(agent._history) == 2
            assert agent._last_saved_count == 2

            agent.llm_manager.generate_with_failover = AsyncMock(return_value="new reply")
            await agent.think("new task")

            # 2 (pre-existing) + 2 (new turn) = 4 — nothing re-appended.
            assert self._row_count(memory, "dup-load") == 4
        finally:
            if os.path.exists(tmp_db):
                os.unlink(tmp_db)

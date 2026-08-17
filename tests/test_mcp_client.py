"""
Tests for the hardened MCP client (Phase 0, task 0.7).

Covers:
- Content-Length framing (spec) and newline-delimited fallback
- Unique request ids / response correlation
- Read timeouts (a silent server must not hang the client)
- JSON-RPC error propagation
- Correct input_schema wiring into the ToolRegistry
"""

import sys
from pathlib import Path

import pytest

from agentfactory.base_tools import ToolRegistry
from agentfactory.mcp_integration import (
    MCPClient,
    MCPServerConfig,
    cleanup_mcp_clients,
    register_mcp_tools,
)

FAKE_SERVER = str(Path(__file__).parent / "mcp_fake_server.py")


def make_config(mode: str = "normal", timeout: float = 5.0) -> MCPServerConfig:
    return MCPServerConfig(name="fake", command=sys.executable, args=[FAKE_SERVER, mode], timeout=timeout)


class TestMCPClient:
    async def test_connect_list_call_close(self):
        client = MCPClient(make_config())
        await client.connect()
        assert client._initialized is True

        tools = await client.list_tools()
        assert len(tools) == 1
        assert tools[0].name == "echo_tool"
        assert tools[0].input_schema["required"] == ["text"]

        result = await client.call_tool("echo_tool", {"text": "hello"})
        assert result == "hello"

        await client.close()

    async def test_newline_framing_fallback(self):
        """Servers that send raw JSON lines (no Content-Length) must still work."""
        client = MCPClient(make_config(mode="newline"))
        await client.connect()
        tools = await client.list_tools()
        assert tools[0].name == "echo_tool"
        await client.close()

    async def test_timeout_raises_instead_of_hanging(self):
        """A server that never responds must raise within the configured timeout."""
        client = MCPClient(make_config(mode="hang", timeout=0.5))
        with pytest.raises(RuntimeError, match="timed out"):
            await client.connect()
        await client.close()

    async def test_jsonrpc_error_is_raised(self):
        client = MCPClient(make_config(mode="error"))
        await client.connect()
        with pytest.raises(RuntimeError, match="boom"):
            await client.call_tool("echo_tool", {"text": "x"})
        await client.close()

    async def test_concurrent_requests_correlate_by_id(self):
        """Out-of-order/overlapping requests must resolve to the right response."""
        client = MCPClient(make_config())
        await client.connect()

        import asyncio

        results = await asyncio.gather(
            client.call_tool("echo_tool", {"text": "one"}),
            client.call_tool("echo_tool", {"text": "two"}),
            client.call_tool("echo_tool", {"text": "three"}),
        )
        assert results == ["one", "two", "three"]
        await client.close()


class TestMCPRegistryWiring:
    async def test_register_mcp_tools_uses_server_input_schema(self):
        registry = ToolRegistry()
        clients = await register_mcp_tools(registry, {"fake": make_config()})

        wrapper = registry.get("echo_tool")
        assert wrapper is not None
        # The schema must come from the MCP server's inputSchema, not internal metadata.
        assert wrapper.signature["properties"]["text"]["type"] == "string"
        assert wrapper.signature["required"] == ["text"]
        assert "metadata" not in wrapper.signature["properties"]

        result = await wrapper.execute({"text": "via registry"})
        assert result == "via registry"

        await cleanup_mcp_clients(clients)
        assert "fake" in clients  # cleanup is best-effort; client dict returned

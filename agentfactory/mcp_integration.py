"""
MCP (Model Context Protocol) Integration.

Provides:
- Discovery of local MCP servers via mcp.json configuration
- Dynamic tool registration for marketplace servers (e.g., @modelcontextprotocol/server-*)
- Custom server support with stdio transport
"""

import os
import re
import json
import asyncio
import structlog
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from agentfactory.base_tools import ToolRegistry, tool, ToolMetadata, SafetyLevel

logger = structlog.get_logger()

# Current stable MCP protocol version (2025-06-18)
MCP_PROTOCOL_VERSION = "2025-06-18"


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server connection."""
    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    timeout: float = 10.0
    enabled: bool = True


@dataclass
class MCPToolInfo:
    """Metadata about a discovered MCP tool."""
    name: str
    description: str
    server_name: str
    input_schema: Dict[str, Any]
    metadata: ToolMetadata


class MCPClient:
    """
    Client for communicating with a single MCP server via stdio.

    Hardened in Phase 0 (task 0.7):
    - Spec-compliant Content-Length framing, with a newline-delimited JSON fallback
      for servers that don't frame messages.
    - Unique request ids with response correlation via a background reader task
      (responses may arrive in any order; server notifications are handled).
    - Read/response timeouts so a silent server can never hang the agent.
    - Modern protocol version + `notifications/initialized` handshake.
    """

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._process: Optional[asyncio.subprocess.Process] = None
        self._read_buffer: bytes = b""
        self._tools: Dict[str, MCPToolInfo] = {}
        self._initialized: bool = False
        self._id_counter: int = 0
        self._pending: Dict[int, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None
        self._closing: bool = False

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self):
        """Connect to the MCP server and perform the initialize handshake."""
        env = os.environ.copy()
        env.update(self.config.env)

        self._process = await asyncio.create_subprocess_exec(
            self.config.command,
            *self.config.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        # Background reader loop dispatches responses to awaiting requests.
        self._reader_task = asyncio.create_task(self._reader_loop())

        result = await self._request(
            "initialize",
            params={
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "agentfactory", "version": "1.0.0"},
            },
        )
        if not result.get("protocolVersion"):
            raise RuntimeError(f"MCP server {self.config.name} failed to initialize")

        # Inform the server the client is initialized (fire-and-forget).
        try:
            await self._send_notification("notifications/initialized", {})
        except Exception as e:
            logger.debug(f"Could not send initialized notification: {e}")

        self._initialized = True
        logger.debug(f"MCP server connected: {self.config.name}")

    async def close(self):
        """Close the MCP connection and clean up pending requests."""
        self._closing = True
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass
        self._fail_pending(RuntimeError("MCP client closed"))
        if self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()

    # ------------------------------------------------------------------
    # Reader loop + framing
    # ------------------------------------------------------------------

    async def _reader_loop(self):
        """Continuously read responses and resolve pending requests by id."""
        while not self._closing:
            try:
                message = await self._read_message()
            except (RuntimeError, asyncio.TimeoutError, json.JSONDecodeError) as e:
                self._fail_pending(e)
                break
            if message is None:
                self._fail_pending(RuntimeError("MCP server connection closed"))
                break

            if "id" in message:
                future = self._pending.pop(message.get("id"), None)
                if future is not None and not future.done():
                    future.set_result(message)
            else:
                # Server notification (e.g. logging) — no request to resolve.
                logger.debug(f"MCP notification from {self.config.name}: {message.get('method')}")

    async def _request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send a JSON-RPC request and await its correlated response."""
        msg_id = self._next_id()
        message: Dict[str, Any] = {"jsonrpc": "2.0", "id": msg_id, "method": method}
        if params is not None:
            message["params"] = params

        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = future
        await self._send_message(message)

        try:
            response = await asyncio.wait_for(future, timeout=self.config.timeout)
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            raise RuntimeError(
                f"MCP request '{method}' timed out after {self.config.timeout}s (server: {self.config.name})"
            )

        if response.get("error"):
            raise RuntimeError(f"MCP error for '{method}' (server: {self.config.name}): {response['error']}")
        return response.get("result", {})

    async def _send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        """Send a JSON-RPC notification (no id — no response expected)."""
        message: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        await self._send_message(message)

    async def _send_message(self, msg: dict):
        """Send a JSON-RPC message using Content-Length framing (MCP stdio spec)."""
        if not self._process:
            raise RuntimeError("MCP client not connected")

        data = json.dumps(msg).encode("utf-8")
        framed = b"Content-Length: " + str(len(data)).encode("ascii") + b"\r\n\r\n" + data
        self._process.stdin.write(framed)
        await self._process.stdin.drain()

    async def _read_message(self) -> Optional[dict]:
        """
        Read one JSON-RPC message from the server.

        Supports Content-Length framing (spec) with a newline-delimited JSON
        fallback for servers that don't frame their output.
        """
        while True:
            message = self._extract_framed_message()
            if message is not None:
                return message
            message = self._extract_newline_message()
            if message is not None:
                return message

            # Read a chunk (Content-Length frames have no trailing newline, so
            # line-based reads would block forever). StreamReader.read(n) returns
            # as soon as data is available, up to n bytes.
            try:
                chunk = await asyncio.wait_for(
                    self._process.stdout.read(4096), timeout=self.config.timeout
                )
            except asyncio.TimeoutError:
                raise RuntimeError(
                    f"MCP server '{self.config.name}' did not respond within {self.config.timeout}s"
                )
            if not chunk:
                return None  # EOF — server closed the stream
            self._read_buffer += chunk

    def _extract_framed_message(self) -> Optional[dict]:
        """Try to parse a Content-Length framed message from the buffer."""
        header_end = self._read_buffer.find(b"\r\n\r\n")
        if header_end == -1:
            return None
        header = self._read_buffer[:header_end]
        match = re.search(br"Content-Length:\s*(\d+)", header)
        if not match:
            return None
        length = int(match.group(1))
        body_start = header_end + 4
        if len(self._read_buffer) < body_start + length:
            return None  # incomplete body — wait for more data
        body = self._read_buffer[body_start:body_start + length]
        self._read_buffer = self._read_buffer[body_start + length:]
        return json.loads(body.decode("utf-8"))

    def _extract_newline_message(self) -> Optional[dict]:
        """Try to parse a newline-delimited JSON message from the buffer (fallback)."""
        stripped = self._read_buffer.lstrip()
        if not stripped.startswith(b"{"):
            return None
        newline = stripped.find(b"\n")
        if newline == -1:
            return None
        candidate = stripped[:newline]
        try:
            obj = json.loads(candidate.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        leading = len(self._read_buffer) - len(stripped)
        consumed = leading + newline + 1
        self._read_buffer = self._read_buffer[consumed:]
        return obj

    def _next_id(self) -> int:
        """Return the next unique request id."""
        self._id_counter += 1
        return self._id_counter

    def _fail_pending(self, error: Exception) -> None:
        """Fail all in-flight requests (connection lost / closed)."""
        pending = list(self._pending.values())
        self._pending.clear()
        for future in pending:
            if not future.done():
                future.set_exception(error)

    # ------------------------------------------------------------------
    # MCP methods
    # ------------------------------------------------------------------

    async def list_tools(self) -> List[MCPToolInfo]:
        """List all available tools from the server."""
        result = await self._request("tools/list")

        tools = []
        for tool_data in result.get("tools", []):
            info = MCPToolInfo(
                name=tool_data["name"],
                description=tool_data.get("description", ""),
                server_name=self.config.name,
                input_schema=tool_data.get("inputSchema", {}),
                metadata=ToolMetadata(
                    name=tool_data["name"],
                    category=f"mcp-{self.config.name}",
                    description=tool_data.get("description", ""),
                    cost_per_call_usd=0.0,
                    safety_level=SafetyLevel.SAFE,
                    tags=["mcp", self.config.name],
                ),
            )
            tools.append(info)
            self._tools[tool_data["name"]] = info

        return tools

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Call a specific tool on the MCP server."""
        result = await self._request(
            "tools/call",
            params={"name": tool_name, "arguments": arguments},
        )

        content = result.get("content", [])

        # Handle MCP tool response format
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text", ""))
            return "\n".join(parts) if parts else str(content)

        return str(content)


# ============================================================
# Configuration Loading
# ============================================================

def load_mcp_config(config_path: str = "mcp.json") -> Dict[str, MCPServerConfig]:
    """
    Load MCP server configurations from mcp.json.

    Returns a dict of server name -> MCPServerConfig.
    """
    config_file = Path(config_path)
    if not config_file.exists():
        logger.warning(f"No MCP config found at {config_path}")
        return {}

    try:
        with open(config_file, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid MCP config: {e}")
        return {}

    servers = {}
    for name, config in data.get("mcpServers", {}).items():
        servers[name] = MCPServerConfig(
            name=name,
            command=config.get("command", config.get("cmd", "")),
            args=config.get("args", []),
            env=config.get("env", {}),
            timeout=config.get("timeout", 10.0),
            enabled=config.get("enabled", True),
        )

    return servers


def create_mcp_config_template(output_path: str = "mcp.json"):
    """Create a sample mcp.json configuration file."""
    template = {
        "mcpServers": {
            "filesystem": {
                "command": "python",
                "args": ["-m", "mcp.server.filesystem"],
                "env": {"FILESYSTEM_BASE_PATH": "/path/to/base"},
                "description": "Filesystem MCP server for file operations",
            },
            "git": {
                "command": "python",
                "args": ["-m", "mcp.server.git"],
                "description": "Git MCP server for repository operations",
            },
        }
    }

    with open(output_path, "w") as f:
        json.dump(template, f, indent=2)

    return template


# ============================================================
# Registry Integration
# ============================================================

async def register_mcp_tools(registry: ToolRegistry, mcp_configs: Dict[str, MCPServerConfig]) -> Dict[str, MCPClient]:
    """
    Register MCP server tools into the given ToolRegistry.

    This is an async function — use `await register_mcp_tools(...)` from async code,
    or `asyncio.run(register_mcp_tools(...))` from synchronous code.

    Returns a dict of connected MCP clients for later cleanup.
    """
    clients: Dict[str, MCPClient] = {}

    for name, config in mcp_configs.items():
        if not config.enabled:
            continue

        logger.info(f"Connecting to MCP server: {name}")
        client = MCPClient(config)

        try:
            await client.connect()
            tools = await client.list_tools()
            clients[name] = client

            for tool_info in tools:
                registry.register_mcp_tool(
                    tool_info.name,
                    tool_info.metadata,
                    server_name=tool_info.server_name,
                    client=client,
                    input_schema=tool_info.input_schema,
                )
                logger.debug(f"Registered MCP tool: {tool_info.name} from {tool_info.server_name}")

        except Exception as e:
            logger.warning(f"Failed to connect to MCP server '{name}': {e}")

    return clients


async def cleanup_mcp_clients(clients: Dict[str, MCPClient]):
    """Clean up all MCP client connections."""
    for name, client in clients.items():
        try:
            await client.close()
            logger.debug(f"Closed MCP client: {name}")
        except Exception as e:
            logger.warning(f"Error closing MCP client '{name}': {e}")

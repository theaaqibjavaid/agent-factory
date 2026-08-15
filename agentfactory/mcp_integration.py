"""
MCP (Model Context Protocol) Integration.

Provides:
- Discovery of local MCP servers via mcp.json configuration
- Dynamic tool registration for marketplace servers (e.g., @modelcontextprotocol/server-*)
- Custom server support with stdio transport
"""

import os
import json
import asyncio
import structlog
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from agentfactory.base_tools import ToolRegistry, tool, ToolMetadata, SafetyLevel

logger = structlog.get_logger()


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
    """Client for communicating with a single MCP server via stdio."""

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._process: Optional[asyncio.subprocess.Process] = None
        self._read_buffer: str = ""
        self._tools: Dict[str, MCPToolInfo] = {}
        self._initialized: bool = False

    async def connect(self):
        """Connect to the MCP server and perform handshake."""
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

        # Send initialize request
        init_msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "0.1",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "agentfactory", "version": "1.0.0"},
            },
        }
        await self._send_message(init_msg)
        response = await self._read_message()

        if response.get("result", {}).get("protocolVersion"):
            self._initialized = True
            logger.debug(f"MCP server connected: {self.config.name}")
        else:
            raise RuntimeError(f"MCP server {self.config.name} failed to initialize")

    async def _send_message(self, msg: dict):
        """Send a JSON-RPC message to the server."""
        if not self._process:
            raise RuntimeError("MCP client not connected")

        data = json.dumps(msg) + "\n"
        self._process.stdin.write(data.encode())
        await self._process.stdin.drain()

    async def _read_message(self) -> dict:
        """Read a JSON-RPC message from the server."""
        if not self._process:
            raise RuntimeError("MCP client not connected")

        while "\n" not in self._read_buffer:
            line = await self._process.stdout.readline()
            if not line:
                raise RuntimeError("MCP server connection closed")
            self._read_buffer += line.decode()

        message_str, self._read_buffer = self._read_buffer.split("\n", 1)
        return json.loads(message_str)

    async def list_tools(self) -> List[MCPToolInfo]:
        """List all available tools from the server."""
        msg = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
        }
        await self._send_message(msg)
        response = await self._read_message()

        tools = []
        for tool_data in response.get("result", {}).get("tools", []):
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
        msg = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }
        await self._send_message(msg)
        response = await self._read_message()

        result = response.get("result", {})
        content = result.get("content", [])

        # Handle MCP tool response format
        if isinstance(content, list):
            parts = []
            for item in content:
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
            return "\n".join(parts) if parts else str(content)

        return str(content)

    async def close(self):
        """Close the MCP connection."""
        if self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()


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

def register_mcp_tools(registry: ToolRegistry, mcp_configs: Dict[str, MCPServerConfig]) -> Dict[str, MCPClient]:
    """
    Register MCP server tools into the given ToolRegistry.

    Returns a dict of connected MCP clients for later cleanup.
    """
    clients: Dict[str, MCPClient] = {}
    loop = asyncio.new_event_loop()

    try:
        for name, config in mcp_configs.items():
            if not config.enabled:
                continue

            logger.info(f"Connecting to MCP server: {name}")
            client = MCPClient(config)

            try:
                loop.run_until_complete(client.connect())
                tools = loop.run_until_complete(client.list_tools())
                clients[name] = client

                for tool_info in tools:
                    registry.register_mcp_tool(
                        tool_info.name,
                        tool_info.metadata,
                        server_name=tool_info.server_name,
                        client=client,
                    )
                    logger.debug(f"Registered MCP tool: {tool_info.name} from {tool_info.server_name}")

            except Exception as e:
                logger.warning(f"Failed to connect to MCP server '{name}': {e}")
    finally:
        # Don't close clients here — they need to stay alive
        pass

    return clients


async def cleanup_mcp_clients(clients: Dict[str, MCPClient]):
    """Clean up all MCP client connections."""
    for name, client in clients.items():
        try:
            await client.close()
            logger.debug(f"Closed MCP client: {name}")
        except Exception as e:
            logger.warning(f"Error closing MCP client '{name}': {e}")

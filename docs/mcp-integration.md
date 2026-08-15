# MCP Integration

AgentFactory supports the [Model Context Protocol](https://modelcontextprotocol.io/) for extending tool capabilities with MCP servers.

## What is MCP?

MCP (Model Context Protocol) is an open standard for connecting AI applications to external tools and data sources. MCP servers provide tools, resources, and prompts that agents can discover and use.

## Configuration

MCP configuration is stored in `mcp.json` at the project root:

```json
{
  "mcpServers": {
    "brave-search": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-brave-search"],
      "env": {
        "BRAVE_API_KEY": "YOUR_BRAVE_API_KEY"
      }
    },
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/allowed/dir"]
    }
  }
}
```

## Creating MCP Config

```bash
# Via CLI
agentfactory init

# Or programmatically
from agentfactory.mcp_integration import create_mcp_config_template
create_mcp_config_template("mcp.json")
```

## Loading MCP Tools

```python
from agentfactory.mcp_integration import MCPClient, load_mcp_config

# Load config
config = load_mcp_config("mcp.json")

# Connect to a server
client = MCPClient("brave-search", config)
await client.connect()

# List available tools
tools = await client.list_tools()

# Call a tool
result = await client.call_tool("brave_web_search", {"query": "AI news"})
```

## Registering MCP Tools as AgentFactory Tools

```python
from agentfactory.base_tools import ToolRegistry, ToolDef, SafetyLevel
from agentfactory.mcp_integration import MCPClient

# Create registry
registry = ToolRegistry()

# Register MCP tools
for tool_name in client.list_tool_names():
    metadata = client.get_tool_metadata(tool_name)
    registry.register_mcp_tool(
        name=tool_name,
        metadata=metadata,
        server_name="brave-search",
        client=client,
    )

# MCP tools appear in list_tools with category "mcp-brave-search"
```

## Available MCP Servers

Popular community MCP servers:
- `@modelcontextprotocol/server-brave-search` — Web search
- `@modelcontextprotocol/server-filesystem` — File system access
- `@modelcontextprotocol/server-git` — Git operations
- `@modelcontextprotocol/server-github` — GitHub API
- `@modelcontextprotocol/server-slack` — Slack integration
- `@modelcontextprotocol/server-discord` — Discord integration

Install with npm:
```bash
npm install -g @modelcontextprotocol/server-brave-search
```

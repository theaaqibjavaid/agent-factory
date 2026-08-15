# CLI Reference

The `agentfactory` command-line interface provides commands for setup, running, and managing agents.

## Commands

### `agentfactory init`

Initialize AgentFactory configuration in the current directory.

```bash
agentfactory init [--force]
```

Creates:
- `.env` — Environment configuration file
- `mcp.json` — MCP server configuration
- `agents/examples/engineer_crew.yaml` — Example agent team config

Options:
- `--force` — Overwrite existing `.env` file

After init, the command validates:
- Python version
- Required dependencies (langchain, fastapi, uvicorn, yaml, structlog)
- API key presence (GEMINI_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY)
- Repository paths (BACKEND_PATH, FRONTEND_PATH, ADMIN_PATH)

---

### `agentfactory run`

Start the FastAPI approval server and background worker simultaneously.

```bash
agentfactory run [--port 8000] [--no-reload] [--worker-only] [--server-only]
```

Options:
- `--port` — Port for the FastAPI server (default: 8000)
- `--reload` / `--no-reload` — Enable/disable auto-reload (default: enabled)
- `--worker-only` — Start only the background worker
- `--server-only` — Start only the FastAPI server

The server runs at `http://localhost:8000` with API docs at `/docs`.

---

### `agentfactory create-agent`

Generate a new agent configuration from template.

```bash
agentfactory create-agent <name> [--rank Senior|Junior|QA|Manager] [--output path]
```

Arguments:
- `name` — Agent name (e.g., `my_code_reviewer`)

Options:
- `--rank` — Agent rank: Senior, Junior, QA, or Manager (default: Junior)
- `--output, -o` — Output file path (default: `agents/<name>.yaml`)

Example:
```bash
agentfactory create-agent my_researcher --rank Senior
```

---

### `agentfactory list-tools`

List all registered tools with metadata.

```bash
agentfactory list-tools
```

Output columns:
- NAME — Tool name
- CATEGORY — Tool category (git, web, file, notify, generic, mcp-*)
- COST — Cost per call in USD
- SAFETY — Safety level (safe, modified, destructive)
- TAGS — Comma-separated tags

---

### `agentfactory status`

Check the current approval server status.

```bash
agentfactory status
```

Connects to `AGENT_SERVER_URL` (default: `http://localhost:8000/api/agent/status`) and reports:
- Connection status (online/offline)
- Current agent status
- Active proposal and branch name
- Last updated timestamp

---

## Global Options

- `--version` / `agentfactory --version` — Show version (1.0.0)

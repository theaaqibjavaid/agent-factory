# Quick Start

Run the AgentFactory Studio — the full platform (API + dashboard) — in one command.

> **The one command you need: `agentfactory studio`.** It starts the v2 platform
> API **and** serves the Studio UI on a single port. Everything else in this
> doc is optional or legacy.

## 1. Install

```bash
# From PyPI (current release)
pip install "agentfactory-studio[platform]"

# Or from source (repo checkout)
pip install -e ".[platform]"
cd web && bun install && cd ..
```

Verify:

```bash
agentfactory --version        # e.g. 1.2.0
```

## 2. Run the whole product — ONE command

```bash
# Pick a JWT secret (required to start the platform)
export AGENTFACTORY_JWT_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"

# Start API + Studio UI on http://localhost:8000 (builds the UI on first run)
agentfactory studio
# or: make studio
```

Open **http://localhost:8000** — that's the Studio dashboard:

1. **Sign up** (first account owns the default workspace).
2. **Agents → create** an agent (rank, role, tools, budget, HITL mode).
3. **Models → connect** a provider with your own API key (`GEMINI_API_KEY` or
   `OPENAI_API_KEY` — or a custom provider URL + key).
4. **Run** a task and watch the live event stream (tokens, tool calls, cost).
5. Add **tools / skills / MCP servers / marketplace items**, use the built-in
   **terminal**, review **approvals**, and manage **memory** (export/import).

Also on the same port: API docs at **http://localhost:8000/docs** and health at
`curl http://localhost:8000/health`.

> Full step-by-step testing guide (every feature, plus the automated suites):
> **[docs/testing.md](testing.md)**.

## 3. Configure LLM API keys (for real agent runs)

At least one provider key, in the environment or in `.env`:

```bash
GEMINI_API_KEY=your-gemini-key-here     # free tier — recommended default
OPENAI_API_KEY=your-openai-key-here
ANTHROPIC_API_KEY=your-anthropic-key-here
```

LLM failover order is Gemini → OpenAI → Anthropic; set as many as you like.
See [docs/env-vars.md](env-vars.md) for the complete reference.

## 4. Optional: enable encryption-at-rest (Phase 8)

```bash
export AGENTFACTORY_ENCRYPTION_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
# back this key up — data written with it is unrecoverable without it
```

## 5. SDK / CLI usage (not the Studio)

Use the SDK as a Python library in your own projects:

```python
from agentfactory.core import AgentFactory

factory = AgentFactory()
agent = factory.create_agent("Senior")
result = await agent.run("Implement user authentication")
```

> ⚠️ The standalone CLI commands (`agentfactory init`, `run`, `create-agent`,
> `list-tools`, `status`, `token`) are the **legacy v1** SDK/approval-server
> flow, kept for backwards compatibility. New projects should use
> `agentfactory studio`.

## Next Steps

- [Local Testing Guide](testing.md) — test every feature end to end
- [Architecture](architecture.md) — understand the design
- [CLI Reference](cli-reference.md) — every command
- [Agent Configuration](agent-config.md) — YAML schema details
- [Writing custom tools](tools.md) — `@tool` decorator and sandboxed code

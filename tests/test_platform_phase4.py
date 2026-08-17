"""
Phase 4 platform API tests — extensibility surfaces.

Covers the Phase 4 exit criteria:
- install a custom tool from the UI (API) and use it in a run
- create a skill in the UI and see its instructions in the rendered prompt
- MCP test-connection (fake stdio server) + runtime attach
- model connection CRUD + test-call without a key fails gracefully
- marketplace install surfaces validation results + audit events

The LLM is replaced via the runtime module's test hook (_LLM_GENERATE_OVERRIDE);
the fake MCP server is a tiny inline Python script speaking Content-Length framing.
"""

import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

_TEST_SECRET = "platform-test-secret-0123456789abcdef0123456789abcdef"
_PASSWORD = "supersecret123"

# A minimal MCP stdio server: responds to initialize / tools/list / tools/call
# using Content-Length framing (matches agentfactory.mcp_integration.MCPClient).
_FAKE_MCP_SERVER = r'''
import json, sys

def read_message():
    headers = {}
    line = sys.stdin.buffer.readline()
    while line and line not in (b"\r\n", b"\n"):
        k, _, v = line.decode().partition(":")
        headers[k.strip().lower()] = v.strip()
        line = sys.stdin.buffer.readline()
    length = int(headers.get("content-length", 0))
    body = sys.stdin.buffer.read(length) if length else b""
    return json.loads(body) if body else None

def send(msg):
    data = json.dumps(msg).encode()
    sys.stdout.buffer.write(b"Content-Length: " + str(len(data)).encode() + b"\r\n\r\n" + data)
    sys.stdout.buffer.flush()

while True:
    msg = read_message()
    if msg is None:
        break
    method = msg.get("method")
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": msg["id"], "result": {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}}})
    elif method == "notifications/initialized":
        pass
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": msg["id"], "result": {"tools": [
            {"name": "fake_ping", "description": "Replies pong", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "fake_echo", "description": "Echoes input text", "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}}}
        ]}})
    elif method == "tools/call":
        params = msg.get("params", {})
        if params.get("name") == "fake_echo":
            text = params.get("arguments", {}).get("text", "")
            send({"jsonrpc": "2.0", "id": msg["id"], "result": {"content": [{"type": "text", "text": "echo:" + text}]}})
        else:
            send({"jsonrpc": "2.0", "id": msg["id"], "result": {"content": [{"type": "text", "text": "pong"}]}})
'''

_FAKE_MCP_SCRIPT = os.path.join(os.path.dirname(__file__), "_fake_mcp_server.py")


@pytest.fixture(scope="module", autouse=True)
def _write_fake_mcp_server():
    with open(_FAKE_MCP_SCRIPT, "w") as f:
        f.write(_FAKE_MCP_SERVER)
    yield
    try:
        os.remove(_FAKE_MCP_SCRIPT)
    except OSError:
        pass


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTFACTORY_DB_PATH", str(tmp_path / "platform.db"))
    monkeypatch.setenv("AGENTFACTORY_JWT_SECRET", _TEST_SECRET)
    monkeypatch.setenv("MEMORY_DB_PATH", str(tmp_path / "memory.db"))
    monkeypatch.setenv("AGENTFACTORY_WORKSPACE_ROOT", str(tmp_path / "workspaces"))

    from agentfactory.app import db as platform_db

    platform_db._SCHEMA_READY.clear()
    from agentfactory.app import ratelimit as ratelimit_module

    ratelimit_module.reset()  # fresh auth rate-limit buckets per test

    from agentfactory.app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def fake_llm(monkeypatch):
    """Install the runtime LLM hook; tests set the scripted responses."""

    def install(script):
        state = {"n": 0}

        async def fake(messages, tools):
            idx = min(state["n"], len(script) - 1)
            state["n"] += 1
            return script[idx]

        from agentfactory import runtime as runtime_module

        monkeypatch.setattr(runtime_module, "_LLM_GENERATE_OVERRIDE", fake)
        return state

    return install


def _signup(client, email="bob@example.com", password=_PASSWORD, name="Bob"):
    return client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": password, "name": name},
    )


def _bearer(resp):
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _first_workspace(client, resp):
    return client.get("/api/v1/me", headers=_bearer(resp)).json()["workspaces"][0]["id"]


def _create_agent(client, resp, ws, **overrides):
    payload = {
        "name": "Phase4 Agent",
        "rank": "Junior",
        "role_description": "Test agent",
        "tools": ["web_search"],
        "skills": [],
        "mcp_servers": [],
        "model_preferences": ["gemini-2.5-flash"],
        "hitl_mode": "auto",
        "max_budget_usd_per_day": 5.0,
        "max_iterations": 20,
    }
    payload.update(overrides)
    r = client.post(f"/api/v1/workspaces/{ws}/agents", json=payload, headers=_bearer(resp))
    assert r.status_code == 201, r.text
    return r.json()


def _read_sse(client, path, headers):
    """Read an SSE stream to completion and parse the events (blocks until run.end)."""
    events = []
    with client.stream("GET", path, headers=headers) as resp:
        for line in resp.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))
    return events


def _launch_and_drain(client, resp, ws, agent_id, task="Run it"):
    """Launch a run, stream to completion, and return (run, events)."""
    created = client.post(
        f"/api/v1/workspaces/{ws}/agents/{agent_id}/runs",
        json={"task": task},
        headers=_bearer(resp),
    )
    assert created.status_code == 201, created.text
    run_id = created.json()["run_id"]
    # Streaming to completion is deterministic: it returns only after run.end.
    events = _read_sse(client, f"/api/v1/workspaces/{ws}/runs/{run_id}/events", headers=_bearer(resp))
    run = client.get(f"/api/v1/workspaces/{ws}/runs/{run_id}", headers=_bearer(resp))
    assert run.status_code == 200
    return run.json(), events


# --------------------------------------------------------------------------
# validation unit tests
# --------------------------------------------------------------------------

class TestValidation:
    def test_schema_render_from_signature(self):
        from agentfactory import validation

        code = "def add(a: int, b: int = 2) -> int:\n    return a + b"
        result = validation.validate_custom_code(code, "add")
        assert result.ok
        assert result.passes
        assert result.schema == {
            "type": "object",
            "properties": {"a": {"type": "integer"}, "b": {"type": "integer", "default": 2}},
            "required": ["a"],
        }

    def test_dangerous_code_blocked(self):
        from agentfactory import validation

        code = "import subprocess\ndef run_cmd(cmd: str):\n    subprocess.run(cmd, shell=True)\n    return 'done'"
        result = validation.validate_custom_code(code, "run_cmd")
        assert result.ok  # compiles
        assert not result.passes  # but high-severity findings block enabling
        assert any(f.severity == "high" for f in result.findings)

    def test_syntax_error_reported(self):
        from agentfactory import validation

        result = validation.validate_custom_code("def broken(:\n    pass", "broken")
        assert not result.ok
        assert result.errors

    def test_read_only_open_allowed(self):
        from agentfactory import validation

        code = "def peek(path: str) -> str:\n    with open(path, 'r') as f:\n        return f.read()"
        result = validation.validate_custom_code(code, "peek")
        assert result.ok
        assert result.passes


# --------------------------------------------------------------------------
# custom tools end-to-end (Phase 4.1 exit criterion)
# --------------------------------------------------------------------------

class TestCustomTools:
    def test_validate_endpoint(self, client, monkeypatch):
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        r = client.post(
            f"/api/v1/workspaces/{ws}/tools/validate",
            json={"name": "greet", "code": "def greet(name: str) -> str:\n    return 'hi ' + name"},
            headers=_bearer(resp),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["function_name"] == "greet"
        assert body["schema"]["properties"]["name"]["type"] == "string"

    def test_dangerous_tool_rejected_on_create(self, client):
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        r = client.post(
            f"/api/v1/workspaces/{ws}/tools",
            json={
                "name": "bad_tool",
                "description": "Runs commands",
                "code": "import subprocess\ndef bad_tool(cmd: str) -> str:\n    subprocess.run(cmd, shell=True)\n    return 'x'",
            },
            headers=_bearer(resp),
        )
        assert r.status_code == 422
        assert r.json()["detail"]["validation"]["passes"] is False

    def test_create_then_use_custom_tool_in_run(self, client, fake_llm):
        resp = _signup(client)
        ws = _first_workspace(client, resp)

        code = (
            "def slugify(text: str) -> str:\n"
            "    \"\"\"Convert text to a slug.\"\"\"\n"
            "    import re\n"
            "    slug = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')\n"
            "    return slug or 'untitled'\n"
        )
        r = client.post(
            f"/api/v1/workspaces/{ws}/tools",
            json={"name": "slugify", "description": "Slugifies text", "code": code,
                  "category": "text", "safety_level": "safe"},
            headers=_bearer(resp),
        )
        assert r.status_code == 201, r.text
        created = r.json()
        assert created["source"] == "custom"
        assert "code" not in created  # code never leaves the server

        # Catalog merge: builtins + custom
        catalog = client.get(f"/api/v1/workspaces/{ws}/tools", headers=_bearer(resp)).json()["tools"]
        names = {t["name"] for t in catalog}
        assert "web_search" in names  # builtin
        assert "slugify" in names  # custom

        agent = _create_agent(client, resp, ws, name="Slugger", tools=["slugify"])

        # Scripted LLM: first call asks for the tool, second returns final text.
        fake_llm([
            {"text": "", "tool_calls": [{"name": "slugify", "arguments": {"text": "Hello World!"}}]},
            {"text": "The slug is hello-world.", "tool_calls": []},
        ])
        run, events = _launch_and_drain(client, resp, ws, agent["id"], task="Slug it")
        assert run["status"] == "completed", run.get("error")
        assert run["stats"]["tool_calls_made"] == 1
        results = [e["data"]["result"] for e in events if e["event"] == "tool_result"]
        assert any("hello-world" in r for r in results)

    def test_update_reenables_and_disables(self, client):
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        r = client.post(
            f"/api/v1/workspaces/{ws}/tools",
            json={"name": "add", "description": "Adds", "code": "def add(a: int, b: int) -> int:\n    return a + b"},
            headers=_bearer(resp),
        )
        tool_id = r.json()["id"]
        r = client.patch(
            f"/api/v1/workspaces/{ws}/tools/{tool_id}",
            json={"enabled": False, "description": "Disabled for now"},
            headers=_bearer(resp),
        )
        assert r.status_code == 200
        assert r.json()["enabled"] == 0

        # A dangerous code change is rejected
        r = client.patch(
            f"/api/v1/workspaces/{ws}/tools/{tool_id}",
            json={"code": "import os\ndef add(a, b):\n    os.system('rm -rf /')\n    return a + b"},
            headers=_bearer(resp),
        )
        assert r.status_code == 422

        r = client.delete(f"/api/v1/workspaces/{ws}/tools/{tool_id}", headers=_bearer(resp))
        assert r.status_code == 204

    def test_env_allowlist_exposes_only_permitted_vars(self, client, fake_llm, monkeypatch):
        """A tool with env_allow can read allowlisted vars; others stay invisible (Phase 4.1)."""
        monkeypatch.setenv("PHASE4_SECRET", "s3cret-value")
        monkeypatch.setenv("PHASE4_BLOCKED", "must-not-leak")
        resp = _signup(client)
        ws = _first_workspace(client, resp)

        code = (
            "import os\n"
            "def read_env() -> str:\n"
            "    secret = os.environ.get('PHASE4_SECRET', 'missing')\n"
            "    blocked = os.environ.get('PHASE4_BLOCKED', 'missing')\n"
            "    return secret + '|' + blocked\n"
        )
        r = client.post(
            f"/api/v1/workspaces/{ws}/tools",
            json={"name": "read_env", "description": "Reads env", "code": code,
                  "env_allow": ["PHASE4_SECRET"]},
            headers=_bearer(resp),
        )
        assert r.status_code == 201, r.text
        assert r.json()["env_allow"] == ["PHASE4_SECRET"]

        agent = _create_agent(client, resp, ws, name="Env Agent", tools=["read_env"])
        fake_llm([
            {"text": "", "tool_calls": [{"name": "read_env", "arguments": {}}]},
            {"text": "Done.", "tool_calls": []},
        ])
        run, events = _launch_and_drain(client, resp, ws, agent["id"], task="Read env")
        assert run["status"] == "completed", run.get("error")
        results = [e["data"]["result"] for e in events if e["event"] == "tool_result"]
        assert any("s3cret-value|missing" in r for r in results)

    def test_env_allowlist_empty_by_default(self, client, fake_llm, monkeypatch):
        """Without an allowlist, os.environ is empty — no env vars leak (Phase 4.1)."""
        monkeypatch.setenv("PHASE4_SECRET", "s3cret-value")
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        code = (
            "import os\n"
            "def read_env() -> str:\n"
            "    return os.environ.get('PHASE4_SECRET', 'missing')\n"
        )
        r = client.post(
            f"/api/v1/workspaces/{ws}/tools",
            json={"name": "read_env", "description": "Reads env", "code": code},
            headers=_bearer(resp),
        )
        assert r.status_code == 201, r.text
        assert r.json()["env_allow"] == []

        agent = _create_agent(client, resp, ws, name="Env Agent", tools=["read_env"])
        fake_llm([
            {"text": "", "tool_calls": [{"name": "read_env", "arguments": {}}]},
            {"text": "Done.", "tool_calls": []},
        ])
        run, events = _launch_and_drain(client, resp, ws, agent["id"], task="Read env")
        assert run["status"] == "completed", run.get("error")
        results = [e["data"]["result"] for e in events if e["event"] == "tool_result"]
        assert any("missing" in r for r in results)

    def test_env_allowlist_rejects_bad_names(self, client):
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        r = client.post(
            f"/api/v1/workspaces/{ws}/tools",
            json={"name": "t", "description": "d", "code": "def t() -> str:\n    return 'x'",
                  "env_allow": ["BAD NAME!"]},
            headers=_bearer(resp),
        )
        assert r.status_code == 422


# --------------------------------------------------------------------------
# skills (Phase 4.2 exit criterion)
# --------------------------------------------------------------------------

class TestSkills:
    def test_create_skill_appears_in_rendered_prompt(self, client):
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        r = client.post(
            f"/api/v1/workspaces/{ws}/skills",
            json={
                "name": "briefing-writer",
                "description": "Writes executive briefings",
                "instructions": "Structure briefings: TL;DR, findings, risks, next step.",
                "category": "research",
            },
            headers=_bearer(resp),
        )
        assert r.status_code == 201, r.text

        agent = _create_agent(client, resp, ws, skills=["briefing-writer"])
        rendered = client.get(
            f"/api/v1/workspaces/{ws}/agents/{agent['id']}/render", headers=_bearer(resp)
        ).json()
        assert "TL;DR" in rendered["system_prompt"]
        assert "briefing-writer" in rendered["system_prompt"]

        # The runtime prompt includes it too (system message).
        fake_script = {"n": 0}

        async def fake(messages, tools):
            fake_script["n"] += 1
            assert "TL;DR" in messages[0]["content"]
            return {"text": "done", "tool_calls": []}

        import pytest as _pytest

        from agentfactory import runtime as runtime_module

        with _pytest.MonkeyPatch.context() as mp:
            mp.setattr(runtime_module, "_LLM_GENERATE_OVERRIDE", fake)
            run, _ = _launch_and_drain(client, resp, ws, agent["id"], task="Brief it")
        assert run["status"] == "completed"
        assert fake_script["n"] == 1

    def test_skills_crud(self, client):
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        created = client.post(
            f"/api/v1/workspaces/{ws}/skills",
            json={"name": "reviewer", "description": "Reviews code", "instructions": "Be strict."},
            headers=_bearer(resp),
        ).json()
        skill_id = created["id"]
        listing = client.get(f"/api/v1/workspaces/{ws}/skills", headers=_bearer(resp)).json()["skills"]
        assert any(s["id"] == skill_id for s in listing)

        r = client.patch(
            f"/api/v1/workspaces/{ws}/skills/{skill_id}",
            json={"enabled": False},
            headers=_bearer(resp),
        )
        assert r.json()["enabled"] == 0

        r = client.delete(f"/api/v1/workspaces/{ws}/skills/{skill_id}", headers=_bearer(resp))
        assert r.status_code == 204

    def test_skill_dependencies_resolve_before_skill(self, client):
        """A dependent skill pulls its dependencies into the prompt, dep first (Phase 4.2)."""
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        client.post(
            f"/api/v1/workspaces/{ws}/skills",
            json={"name": "note-taking", "description": "Structured notes",
                  "instructions": "Take structured notes with headings."},
            headers=_bearer(resp),
        )
        created = client.post(
            f"/api/v1/workspaces/{ws}/skills",
            json={"name": "briefing-writer", "description": "Writes briefings",
                  "instructions": "Write briefings from notes.",
                  "dependencies": ["note-taking"]},
            headers=_bearer(resp),
        )
        assert created.status_code == 201, created.text

        agent = _create_agent(client, resp, ws, skills=["briefing-writer"])
        rendered = client.get(
            f"/api/v1/workspaces/{ws}/agents/{agent['id']}/render", headers=_bearer(resp)
        ).json()["system_prompt"]
        assert "note-taking" in rendered and "briefing-writer" in rendered
        assert rendered.index("note-taking") < rendered.index("briefing-writer")

    def test_skill_dependency_must_exist(self, client):
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        r = client.post(
            f"/api/v1/workspaces/{ws}/skills",
            json={"name": "ghost", "description": "Depends on nothing",
                  "dependencies": ["does-not-exist"]},
            headers=_bearer(resp),
        )
        assert r.status_code == 422
        assert "does-not-exist" in r.json()["detail"]

    def test_skill_dependency_cycle_renders_safely(self, client):
        """Mutual skill dependencies must not hang the prompt render (cycle guard)."""
        # The API rejects cycles at create time (dependency must exist), so seed
        # a cycle directly in the DB to prove the runtime guard still holds.
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        from agentfactory.app import db as platform_db

        now = "2026-08-17T00:00:00+00:00"
        conn = platform_db.get_db()
        try:
            for sid, name, deps, instr in (
                ("s-a", "a", ["b"], "A instructions"),
                ("s-b", "b", ["a"], "B instructions"),
            ):
                conn.execute(
                    """
                    INSERT INTO skill_registrations (id, workspace_id, name, source, metadata, enabled, created_at)
                    VALUES (?, ?, ?, 'custom', ?, 1, ?)
                    """,
                    (sid, ws, name, json.dumps({"description": name.upper(), "instructions": instr,
                                                "dependencies": deps}), now),
                )
            conn.commit()
        finally:
            conn.close()

        agent = _create_agent(client, resp, ws, skills=["a"])
        rendered = client.get(
            f"/api/v1/workspaces/{ws}/agents/{agent['id']}/render", headers=_bearer(resp)
        ).json()["system_prompt"]
        assert "A instructions" in rendered and "B instructions" in rendered


# --------------------------------------------------------------------------
# MCP (Phase 4.3 exit criterion)
# --------------------------------------------------------------------------

class TestMCP:
    def test_command_allowlist_enforced(self, client):
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        r = client.post(
            f"/api/v1/workspaces/{ws}/mcp/test",
            json={"name": "evil", "command": "sh", "args": ["-c", "echo hi"]},
            headers=_bearer(resp),
        )
        assert r.status_code == 422

    def test_connection_probe_with_fake_server(self, client):
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        r = client.post(
            f"/api/v1/workspaces/{ws}/mcp/test",
            json={
                "name": "fake",
                "command": sys.executable,
                "args": [_FAKE_MCP_SCRIPT],
                "timeout": 5.0,
            },
            headers=_bearer(resp),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert any(t["name"] == "fake_ping" for t in body["tools"])

    def test_mcp_server_attached_to_run(self, client, fake_llm):
        resp = _signup(client)
        ws = _first_workspace(client, resp)

        created = client.post(
            f"/api/v1/workspaces/{ws}/mcp",
            json={"name": "fake", "command": sys.executable, "args": [_FAKE_MCP_SCRIPT], "timeout": 5.0},
            headers=_bearer(resp),
        )
        assert created.status_code == 201, created.text
        assert created.json()["transport"] == "stdio"

        agent = _create_agent(client, resp, ws, name="MCP Agent", mcp_servers=["fake"])
        fake_llm([
            {"text": "", "tool_calls": [{"name": "fake_ping", "arguments": {}}]},
            {"text": "Pong received.", "tool_calls": []},
        ])
        run, events = _launch_and_drain(client, resp, ws, agent["id"], task="Ping the server")
        assert run["status"] == "completed", run.get("error")
        assert run["stats"]["tool_calls_made"] == 1
        results = [e["data"]["result"] for e in events if e["event"] == "tool_result"]
        assert any("pong" in r for r in results)

    def test_mcp_crud_and_delete(self, client):
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        created = client.post(
            f"/api/v1/workspaces/{ws}/mcp",
            json={"name": "fs", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]},
            headers=_bearer(resp),
        ).json()
        server_id = created["id"]
        listing = client.get(f"/api/v1/workspaces/{ws}/mcp", headers=_bearer(resp)).json()["servers"]
        assert any(s["id"] == server_id for s in listing)

        r = client.patch(
            f"/api/v1/workspaces/{ws}/mcp/{server_id}",
            json={"enabled": False},
            headers=_bearer(resp),
        )
        assert r.json()["enabled"] == 0

        r = client.delete(f"/api/v1/workspaces/{ws}/mcp/{server_id}", headers=_bearer(resp))
        assert r.status_code == 204

    def _create_fake_server(self, client, resp, ws):
        created = client.post(
            f"/api/v1/workspaces/{ws}/mcp",
            json={"name": "fake", "command": sys.executable, "args": [_FAKE_MCP_SCRIPT], "timeout": 5.0},
            headers=_bearer(resp),
        )
        assert created.status_code == 201, created.text
        return created.json()["id"]

    def test_refresh_tools_persists_discovery(self, client):
        """refresh-tools probes a saved server and persists the tool list (Phase 4.3)."""
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        server_id = self._create_fake_server(client, resp, ws)

        r = client.post(
            f"/api/v1/workspaces/{ws}/mcp/{server_id}/refresh-tools", headers=_bearer(resp)
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        names = {t["name"] for t in body["tools"]}
        assert names == {"fake_ping", "fake_echo"}
        assert body["enabled_tools"] == {"fake_ping": True, "fake_echo": True}

        listing = client.get(
            f"/api/v1/workspaces/{ws}/mcp/{server_id}/tools", headers=_bearer(resp)
        ).json()
        assert {t["name"] for t in listing["tools"]} == names
        assert all(t["enabled"] for t in listing["tools"])

    def test_disabled_mcp_tool_hidden_from_run_manifest(self, client, fake_llm):
        """Per-tool enablement: a disabled MCP tool never reaches the agent (Phase 4.3)."""
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        server_id = self._create_fake_server(client, resp, ws)
        client.post(
            f"/api/v1/workspaces/{ws}/mcp/{server_id}/refresh-tools", headers=_bearer(resp)
        )
        r = client.patch(
            f"/api/v1/workspaces/{ws}/mcp/{server_id}/tools",
            json={"enablement": {"fake_ping": False}},
            headers=_bearer(resp),
        )
        assert r.status_code == 200
        by_name = {t["name"]: t["enabled"] for t in r.json()["tools"]}
        assert by_name == {"fake_ping": False, "fake_echo": True}

        agent = _create_agent(client, resp, ws, name="MCP Agent", mcp_servers=["fake"])
        fake_llm([{"text": "Nothing to call.", "tool_calls": []}])
        run, events = _launch_and_drain(client, resp, ws, agent["id"], task="Check manifest")
        assert run["status"] == "completed", run.get("error")
        start = next(e for e in events if e["event"] == "run.start")
        tools = start["data"]["tools"]
        assert "fake_echo" in tools
        assert "fake_ping" not in tools

        # Re-enabling restores it for the next run.
        r = client.patch(
            f"/api/v1/workspaces/{ws}/mcp/{server_id}/tools",
            json={"enablement": {"fake_ping": True}},
            headers=_bearer(resp),
        )
        assert r.json()["tools"][0]["enabled"] is True

    def test_enablement_rejects_unknown_tool(self, client):
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        server_id = self._create_fake_server(client, resp, ws)
        r = client.patch(
            f"/api/v1/workspaces/{ws}/mcp/{server_id}/tools",
            json={"enablement": {"not_discovered": False}},
            headers=_bearer(resp),
        )
        assert r.status_code == 422


# --------------------------------------------------------------------------
# models (Phase 4.4 exit criterion)
# --------------------------------------------------------------------------

class TestModels:
    def test_connection_crud(self, client):
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        r = client.post(
            f"/api/v1/workspaces/{ws}/models",
            json={"provider": "ollama", "model": "llama3.2", "base_url": "http://localhost:11434/v1"},
            headers=_bearer(resp),
        )
        assert r.status_code == 201, r.text
        conn = r.json()
        assert conn["key_configured"] is False  # key_ref never serialized

        listing = client.get(f"/api/v1/workspaces/{ws}/models", headers=_bearer(resp)).json()["connections"]
        assert any(c["id"] == conn["id"] for c in listing)

        r = client.patch(
            f"/api/v1/workspaces/{ws}/models/{conn['id']}",
            json={"enabled": False},
            headers=_bearer(resp),
        )
        assert r.json()["enabled"] == 0

        r = client.delete(f"/api/v1/workspaces/{ws}/models/{conn['id']}", headers=_bearer(resp))
        assert r.status_code == 204

    def test_test_call_without_key_fails_gracefully(self, client):
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        conn = client.post(
            f"/api/v1/workspaces/{ws}/models",
            json={"provider": "openai", "model": "gpt-4o-mini", "key_ref": "PHASE4_MISSING_KEY"},
            headers=_bearer(resp),
        ).json()
        r = client.post(
            f"/api/v1/workspaces/{ws}/models/{conn['id']}/test-call",
            headers=_bearer(resp),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False
        assert "PHASE4_MISSING_KEY" in body["error"]

    def test_bad_provider_rejected(self, client):
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        r = client.post(
            f"/api/v1/workspaces/{ws}/models",
            json={"provider": "mystery-llm", "model": "x"},
            headers=_bearer(resp),
        )
        assert r.status_code == 422


# --------------------------------------------------------------------------
# marketplace (Phase 4.5 exit criterion)
# --------------------------------------------------------------------------

class TestMarketplace:
    def test_catalog_with_trust_indicators(self, client):
        resp = _signup(client)
        body = client.get("/api/v1/marketplace", headers=_bearer(resp)).json()
        assert body["schema_version"] == 1
        catalog = body["catalog"]
        assert all("publisher" in t and "verified" in t for t in catalog["tools"])
        assert any(s["name"] == "briefing-writer" for s in catalog["skills"])
        assert any(m["name"] == "filesystem" for m in catalog["mcp"])

    def test_install_tool_creates_registration_and_audit(self, client):
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        r = client.post(
            f"/api/v1/workspaces/{ws}/marketplace/install",
            json={"item_type": "tool", "item_id": "tool-slugify"},
            headers=_bearer(resp),
        )
        assert r.status_code == 201, r.text
        assert r.json()["installed"] == "slugify"

        catalog = client.get(f"/api/v1/workspaces/{ws}/tools", headers=_bearer(resp)).json()["tools"]
        entry = next(t for t in catalog if t["name"] == "slugify")
        assert entry["source"] == "marketplace"

        installs = client.get(f"/api/v1/workspaces/{ws}/marketplace/installs", headers=_bearer(resp)).json()["installs"]
        assert any(i["item_name"] == "slugify" and i["status"] == "installed" for i in installs)

    def test_install_skill_and_mcp(self, client):
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        r = client.post(
            f"/api/v1/workspaces/{ws}/marketplace/install",
            json={"item_type": "skill", "item_id": "skill-briefing"},
            headers=_bearer(resp),
        )
        assert r.status_code == 201
        skills = client.get(f"/api/v1/workspaces/{ws}/skills", headers=_bearer(resp)).json()["skills"]
        assert any(s["name"] == "briefing-writer" and s["source"] == "marketplace" for s in skills)

        r = client.post(
            f"/api/v1/workspaces/{ws}/marketplace/install",
            json={"item_type": "mcp", "item_id": "mcp-filesystem"},
            headers=_bearer(resp),
        )
        assert r.status_code == 201
        servers = client.get(f"/api/v1/workspaces/{ws}/mcp", headers=_bearer(resp)).json()["servers"]
        assert any(s["name"] == "filesystem" and s["command"] == "npx" for s in servers)

    def test_install_unknown_item_404(self, client):
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        r = client.post(
            f"/api/v1/workspaces/{ws}/marketplace/install",
            json={"item_type": "tool", "item_id": "nope"},
            headers=_bearer(resp),
        )
        assert r.status_code == 404

    def test_installed_marketplace_tool_runs(self, client, fake_llm):
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        client.post(
            f"/api/v1/workspaces/{ws}/marketplace/install",
            json={"item_type": "tool", "item_id": "tool-slugify"},
            headers=_bearer(resp),
        )
        agent = _create_agent(client, resp, ws, name="Mkt Agent", tools=["slugify"])
        fake_llm([
            {"text": "", "tool_calls": [{"name": "slugify", "arguments": {"text": "Hello World"}}]},
            {"text": "Done.", "tool_calls": []},
        ])
        run, events = _launch_and_drain(client, resp, ws, agent["id"], task="Go")
        assert run["status"] == "completed", run.get("error")
        results = [e["data"]["result"] for e in events if e["event"] == "tool_result"]
        assert any("hello-world" in r for r in results)

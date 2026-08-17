"""
Phase 2 platform API tests.

Covers the Phase 2 exit criteria end to end over the API:
- streamed run from API (SSE events: run.start/token/tool_call/tool_result/verify/cost/run.end)
  with tool calls and cost stats
- HITL gate flow: gate run -> proposal -> approve/reject/modify -> execution
- FAILED recovery via retry
- memory export/import round-trip (versioned bundle)
- agent render endpoint (system prompt + tool manifest)

The LLM is replaced via the runtime module's test hook (_LLM_GENERATE_OVERRIDE),
so no API keys or network calls are involved.
"""

import json

import pytest
from fastapi.testclient import TestClient

_TEST_SECRET = "platform-test-secret-0123456789abcdef0123456789abcdef"
_PASSWORD = "supersecret123"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTFACTORY_DB_PATH", str(tmp_path / "platform.db"))
    monkeypatch.setenv("AGENTFACTORY_JWT_SECRET", _TEST_SECRET)
    monkeypatch.setenv("MEMORY_DB_PATH", str(tmp_path / "memory.db"))

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


def _signup(client, email="alice@example.com", password=_PASSWORD, name="Alice"):
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
        "name": "Phase2 Agent",
        "rank": "Junior",
        "role_description": "Test agent",
        "system_instructions": "You are a Phase 2 test agent.",
        "model_preferences": ["gemini-2.5-flash"],
        "tools": [],
        "hitl_mode": "auto",
        "max_iterations": 5,
    }
    payload.update(overrides)
    r = client.post(f"/api/v1/workspaces/{ws}/agents", json=payload, headers=_bearer(resp))
    assert r.status_code == 201
    return r.json()


def _read_sse(client, url, headers):
    """Read an SSE stream to completion and parse the events."""
    events = []
    with client.stream("GET", url, headers=headers) as r:
        assert r.status_code == 200, r.text
        for line in r.iter_lines():
            if line and line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))
    return events


# --------------------------------------------------------------------------
# Render + streamed runs (2.1/2.2)
# --------------------------------------------------------------------------

class TestRender:
    def test_render_endpoint(self, client):
        r = _signup(client)
        ws = _first_workspace(client, r)
        agent = _create_agent(client, r, ws, tools=["read_text_file"])

        rendered = client.get(f"/api/v1/workspaces/{ws}/agents/{agent['id']}/render", headers=_bearer(r))
        assert rendered.status_code == 200
        data = rendered.json()
        assert "You are a Phase 2 test agent." in data["system_prompt"]
        assert "read_text_file" in data["system_prompt"]
        assert data["tools"][0]["name"] == "read_text_file"
        assert data["tools"][0]["safety"] == "safe"
        assert data["hitl_mode"] == "auto"

    def test_render_404_for_other_workspace_agent(self, client):
        alice = _signup(client, email="alice@example.com")
        bob = _signup(client, email="bob@example.com", name="Bob")
        alice_ws = _first_workspace(client, alice)
        agent = _create_agent(client, alice, alice_ws)
        r = client.get(f"/api/v1/workspaces/{alice_ws}/agents/{agent['id']}/render", headers=_bearer(bob))
        assert r.status_code == 403


class TestStreamedRun:
    def test_final_answer_run_via_sse(self, client, fake_llm):
        fake_llm([{"text": "The answer is 42.", "tool_calls": []}])
        r = _signup(client)
        ws = _first_workspace(client, r)
        agent = _create_agent(client, r, ws)

        created = client.post(
            f"/api/v1/workspaces/{ws}/agents/{agent['id']}/runs",
            json={"task": "What is the answer?"},
            headers=_bearer(r),
        )
        assert created.status_code == 201
        run_id = created.json()["run_id"]
        assert created.json()["status"] == "running"

        events = _read_sse(client, f"/api/v1/workspaces/{ws}/runs/{run_id}/events", headers=_bearer(r))
        names = [e["event"] for e in events]
        assert "run.start" in names
        assert "token" in names
        assert "verify" in names
        assert "cost" in names
        assert "run.end" in names
        end = next(e for e in events if e["event"] == "run.end")
        assert end["data"]["status"] == "completed"
        assert end["data"]["result"] == "The answer is 42."

        detail = client.get(f"/api/v1/workspaces/{ws}/runs/{run_id}", headers=_bearer(r)).json()
        assert detail["status"] == "completed"
        assert detail["result"] == "The answer is 42."
        assert detail["stats"]["iterations"] == 1

    def test_tool_call_run_via_sse(self, client, fake_llm, monkeypatch):
        """Agent calls a real tool, gets a result, then answers."""
        from agentfactory.base_tools import SafetyLevel, ToolDef, register_tool, _TOOL_REGISTRY

        name = "phase2_echo"

        def echo(text: str) -> str:
            return f"echo:{text}"

        register_tool(ToolDef(
            name=name, func=echo, description="Echoes text",
            args_schema={"properties": {"text": {"type": "string"}}, "required": ["text"]},
            safety_level=SafetyLevel.SAFE, cost_per_call_usd=0.05,
        ))

        try:
            fake_llm([
                {"text": "", "tool_calls": [{"name": name, "arguments": {"text": "ping"}, "id": "1"}]},
                {"text": "I echoed it.", "tool_calls": []},
            ])
            r = _signup(client)
            ws = _first_workspace(client, r)
            agent = _create_agent(client, r, ws, tools=[name])

            created = client.post(
                f"/api/v1/workspaces/{ws}/agents/{agent['id']}/runs",
                json={"task": "echo ping"},
                headers=_bearer(r),
            )
            run_id = created.json()["run_id"]

            events = _read_sse(client, f"/api/v1/workspaces/{ws}/runs/{run_id}/events", headers=_bearer(r))
            names = [e["event"] for e in events]
            assert "tool_call" in names and "tool_result" in names
            tool_result = next(e for e in events if e["event"] == "tool_result")
            assert tool_result["data"]["result"] == "echo:ping"

            detail = client.get(f"/api/v1/workspaces/{ws}/runs/{run_id}", headers=_bearer(r)).json()
            assert detail["stats"]["tool_calls_made"] == 1
            assert detail["stats"]["total_cost_usd"] == 0.05
        finally:
            _TOOL_REGISTRY.pop(name, None)

    def test_run_requires_membership(self, client, fake_llm):
        fake_llm([{"text": "ok", "tool_calls": []}])
        alice = _signup(client, email="alice@example.com")
        bob = _signup(client, email="bob@example.com", name="Bob")
        alice_ws = _first_workspace(client, alice)
        agent = _create_agent(client, alice, alice_ws)

        r = client.post(
            f"/api/v1/workspaces/{alice_ws}/agents/{agent['id']}/runs",
            json={"task": "sneaky"},
            headers=_bearer(bob),
        )
        assert r.status_code == 403


# --------------------------------------------------------------------------
# HITL gate (2.3)
# --------------------------------------------------------------------------

class TestHitlGate:
    def test_gate_run_waits_for_approval_then_executes(self, client, fake_llm):
        fake_llm([{"text": "Approved task complete.", "tool_calls": []}])
        r = _signup(client)
        ws = _first_workspace(client, r)
        agent = _create_agent(client, r, ws, hitl_mode="gate")

        created = client.post(
            f"/api/v1/workspaces/{ws}/agents/{agent['id']}/runs",
            json={"task": "Implement the feature"},
            headers=_bearer(r),
        )
        assert created.status_code == 201
        assert created.json()["status"] == "pending_approval"
        proposal_id = created.json()["proposal_id"]
        run_id = created.json()["run_id"]

        # Proposal appears in the inbox
        inbox = client.get(f"/api/v1/workspaces/{ws}/proposals", headers=_bearer(r)).json()["proposals"]
        assert any(p["id"] == proposal_id and p["status"] == "pending" for p in inbox)

        # Run stays pending until approved
        run = client.get(f"/api/v1/workspaces/{ws}/runs/{run_id}", headers=_bearer(r)).json()
        assert run["status"] == "pending_approval"

        # Approve -> execution starts -> SSE completes
        review = client.post(
            f"/api/v1/workspaces/{ws}/proposals/{proposal_id}/review",
            json={"action": "approve", "notes": "Looks good"},
            headers=_bearer(r),
        )
        assert review.status_code == 200
        assert review.json()["run_id"] == run_id

        events = _read_sse(client, f"/api/v1/workspaces/{ws}/runs/{run_id}/events", headers=_bearer(r))
        end = next(e for e in events if e["event"] == "run.end")
        assert end["data"]["status"] == "completed"

        proposal = client.get(f"/api/v1/workspaces/{ws}/proposals/{proposal_id}", headers=_bearer(r)).json()
        assert proposal["status"] == "approved"

    def test_reject_cancels_run(self, client, fake_llm):
        fake_llm([{"text": "never runs", "tool_calls": []}])
        r = _signup(client)
        ws = _first_workspace(client, r)
        agent = _create_agent(client, r, ws, hitl_mode="gate")

        created = client.post(
            f"/api/v1/workspaces/{ws}/agents/{agent['id']}/runs",
            json={"task": "Something risky"},
            headers=_bearer(r),
        ).json()
        proposal_id = created["proposal_id"]
        run_id = created["run_id"]

        review = client.post(
            f"/api/v1/workspaces/{ws}/proposals/{proposal_id}/review",
            json={"action": "reject", "notes": "No thanks"},
            headers=_bearer(r),
        )
        assert review.json()["status"] == "rejected"

        run = client.get(f"/api/v1/workspaces/{ws}/runs/{run_id}", headers=_bearer(r)).json()
        assert run["status"] == "cancelled"

        # Cannot review twice
        again = client.post(
            f"/api/v1/workspaces/{ws}/proposals/{proposal_id}/review",
            json={"action": "approve"},
            headers=_bearer(r),
        )
        assert again.status_code == 409

    def test_modify_updates_plan(self, client, fake_llm):
        fake_llm([{"text": "done", "tool_calls": []}])
        r = _signup(client)
        ws = _first_workspace(client, r)
        agent = _create_agent(client, r, ws, hitl_mode="gate")

        created = client.post(
            f"/api/v1/workspaces/{ws}/agents/{agent['id']}/runs",
            json={"task": "Original plan"},
            headers=_bearer(r),
        ).json()
        proposal_id = created["proposal_id"]

        review = client.post(
            f"/api/v1/workspaces/{ws}/proposals/{proposal_id}/review",
            json={"action": "modify", "notes": "Amended instructions"},
            headers=_bearer(r),
        )
        assert review.json()["status"] == "modified"

        proposal = client.get(f"/api/v1/workspaces/{ws}/proposals/{proposal_id}", headers=_bearer(r)).json()
        assert proposal["status"] == "modified"
        assert "Amended instructions" in proposal["plan"]


# --------------------------------------------------------------------------
# Retry / FAILED recovery (2.6)
# --------------------------------------------------------------------------

class TestRetry:
    def test_failed_run_can_be_retried(self, client, monkeypatch):
        state = {"calls": 0}

        async def flaky(messages, tools):
            state["calls"] += 1
            if state["calls"] == 1:
                raise RuntimeError("model unavailable")
            return {"text": "recovered", "tool_calls": []}

        from agentfactory import runtime as runtime_module

        monkeypatch.setattr(runtime_module, "_LLM_GENERATE_OVERRIDE", flaky)

        r = _signup(client)
        ws = _first_workspace(client, r)
        agent = _create_agent(client, r, ws)

        created = client.post(
            f"/api/v1/workspaces/{ws}/agents/{agent['id']}/runs",
            json={"task": "flaky task"},
            headers=_bearer(r),
        ).json()
        run_id = created["run_id"]

        events = _read_sse(client, f"/api/v1/workspaces/{ws}/runs/{run_id}/events", headers=_bearer(r))
        end = next(e for e in events if e["event"] == "run.end")
        assert end["data"]["status"] == "failed"

        run = client.get(f"/api/v1/workspaces/{ws}/runs/{run_id}", headers=_bearer(r)).json()
        assert run["status"] == "failed"
        assert "model unavailable" in run["error"]

        # Retry now succeeds (the fake recovered)
        retry = client.post(f"/api/v1/workspaces/{ws}/runs/{run_id}/retry", headers=_bearer(r))
        assert retry.status_code == 200
        assert retry.json()["retries"] == 1

        events = _read_sse(client, f"/api/v1/workspaces/{ws}/runs/{run_id}/events", headers=_bearer(r))
        end = next(e for e in events if e["event"] == "run.end")
        assert end["data"]["status"] == "completed"

        run = client.get(f"/api/v1/workspaces/{ws}/runs/{run_id}", headers=_bearer(r)).json()
        assert run["status"] == "completed"
        assert run["retries"] == 1
        assert run["result"] == "recovered"

    def test_cannot_retry_completed_run(self, client, fake_llm):
        fake_llm([{"text": "fine", "tool_calls": []}])
        r = _signup(client)
        ws = _first_workspace(client, r)
        agent = _create_agent(client, r, ws)

        created = client.post(
            f"/api/v1/workspaces/{ws}/agents/{agent['id']}/runs",
            json={"task": "ok task"},
            headers=_bearer(r),
        ).json()
        run_id = created["run_id"]
        _read_sse(client, f"/api/v1/workspaces/{ws}/runs/{run_id}/events", headers=_bearer(r))

        retry = client.post(f"/api/v1/workspaces/{ws}/runs/{run_id}/retry", headers=_bearer(r))
        assert retry.status_code == 409


# --------------------------------------------------------------------------
# Memory service (2.4)
# --------------------------------------------------------------------------

class TestMemoryService:
    def _memory_url(self, ws, agent_id):
        return f"/api/v1/workspaces/{ws}/agents/{agent_id}/memory"

    def test_save_list_delete_fact(self, client):
        r = _signup(client)
        ws = _first_workspace(client, r)
        agent = _create_agent(client, r, ws)

        saved = client.post(
            f"{self._memory_url(ws, agent['id'])}/facts",
            json={"key": "user_name", "value": "Alice", "fact_type": "string"},
            headers=_bearer(r),
        )
        assert saved.status_code == 201

        memory = client.get(self._memory_url(ws, agent["id"]), headers=_bearer(r)).json()
        assert memory["facts"]["user_name"] == "Alice"
        assert memory["stats"]["message_count"] == 0

        deleted = client.delete(
            f"{self._memory_url(ws, agent['id'])}/facts/user_name", headers=_bearer(r)
        )
        assert deleted.status_code == 200
        memory = client.get(self._memory_url(ws, agent["id"]), headers=_bearer(r)).json()
        assert "user_name" not in memory["facts"]

    def test_export_import_round_trip(self, client):
        r = _signup(client)
        ws = _first_workspace(client, r)
        agent = _create_agent(client, r, ws)
        headers = _bearer(r)

        # Seed facts + history
        client.post(
            f"{self._memory_url(ws, agent['id'])}/facts",
            json={"key": "preferred_language", "value": "python"},
            headers=headers,
        )
        client.post(
            f"{self._memory_url(ws, agent['id'])}/facts",
            json={"key": "retry_count", "value": 3, "fact_type": "int"},
            headers=headers,
        )
        # history via a real run
        from agentfactory import runtime as runtime_module

        async def llm(messages, tools):
            return {"text": "hello from memory land", "tool_calls": []}

        original = runtime_module._LLM_GENERATE_OVERRIDE
        runtime_module._LLM_GENERATE_OVERRIDE = llm
        try:
            created = client.post(
                f"/api/v1/workspaces/{ws}/agents/{agent['id']}/runs",
                json={"task": "remember this"},
                headers=headers,
            ).json()
            run_id = created["run_id"]
            _read_sse(client, f"/api/v1/workspaces/{ws}/runs/{run_id}/events", headers=headers)
        finally:
            runtime_module._LLM_GENERATE_OVERRIDE = original

        exported = client.get(f"{self._memory_url(ws, agent['id'])}/export", headers=headers).json()
        assert exported["schema_version"] == 1
        assert exported["facts"]["preferred_language"] == "python"
        assert exported["facts"]["retry_count"] == 3
        assert any("hello from memory land" in m["content"] for m in exported["history"])

        # Wipe then restore from the bundle
        cleared = client.post(
            f"{self._memory_url(ws, agent['id'])}/clear",
            json={"confirm": "DELETE"},
            headers=headers,
        )
        assert cleared.status_code == 200
        assert cleared.json()["deleted_messages"] > 0

        imported = client.post(
            f"{self._memory_url(ws, agent['id'])}/import",
            json={"bundle": exported, "mode": "replace"},
            headers=headers,
        )
        assert imported.status_code == 200
        assert imported.json()["imported"]["facts"] == 2

        memory = client.get(self._memory_url(ws, agent["id"]), headers=headers).json()
        assert memory["facts"]["preferred_language"] == "python"
        assert memory["facts"]["retry_count"] == 3
        assert any("hello from memory land" in m["content"] for m in memory["history"])

    def test_clear_requires_confirmation(self, client):
        r = _signup(client)
        ws = _first_workspace(client, r)
        agent = _create_agent(client, r, ws)

        bad = client.post(
            f"{self._memory_url(ws, agent['id'])}/clear",
            json={"confirm": "nope"},
            headers=_bearer(r),
        )
        assert bad.status_code == 422

    def test_import_rejects_wrong_schema_version(self, client):
        r = _signup(client)
        ws = _first_workspace(client, r)
        agent = _create_agent(client, r, ws)

        bad = client.post(
            f"{self._memory_url(ws, agent['id'])}/import",
            json={"bundle": {"schema_version": 99, "history": [], "facts": {}}, "mode": "merge"},
            headers=_bearer(r),
        )
        assert bad.status_code == 422

    def test_memory_isolated_per_workspace(self, client):
        alice = _signup(client, email="alice@example.com")
        bob = _signup(client, email="bob@example.com", name="Bob")
        alice_ws = _first_workspace(client, alice)
        agent = _create_agent(client, alice, alice_ws)

        # Bob cannot read Alice's agent memory (agent not in Bob's workspace scope)
        r = client.get(f"{self._memory_url(alice_ws, agent['id'])}", headers=_bearer(bob))
        assert r.status_code == 403

        # Even direct agent_id access is scoped: Bob's workspace has no such agent
        bob_ws = _first_workspace(client, bob)
        r = client.get(f"{self._memory_url(bob_ws, agent['id'])}", headers=_bearer(bob))
        assert r.status_code == 404

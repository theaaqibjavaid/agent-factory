"""
Phase 5 platform tests — terminal, observability, autonomy, notifications.

Covers the Phase 5 exit criteria:
- terminal session works end-to-end (create/write/output/kill + WS transport),
  destructive commands require explicit confirmation
- run events persist and cost/token/budget dashboards aggregate from agent_runs;
  budget alerts fire at 80%/100%
- constitutional rules render into the system prompt; branch protection and
  path allowlists block dangerous tool calls before execution
- gated proposals and completed runs notify Discord/Gmail/webhook when the
  workspace configures notification channels (reusing notify_tools)

The LLM is replaced via the runtime test hook; notification dispatch is made
synchronous via a monkeypatched ``_fire`` so assertions are deterministic.
"""

import json
import time

import pytest
from fastapi.testclient import TestClient

_TEST_SECRET = "platform-test-secret-0123456789abcdef0123456789abcdef"
_PASSWORD = "supersecret123"


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


@pytest.fixture
def sync_notify(monkeypatch):
    """Run notification dispatch synchronously so tests are deterministic."""
    from agentfactory.app import notify as notify_module

    monkeypatch.setattr(notify_module, "_fire", lambda target, *a, **kw: target(*a, **kw))


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
        "name": "Phase5 Agent",
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
    events = []
    with client.stream("GET", path, headers=headers) as resp:
        for line in resp.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))
    return events


def _launch_and_drain(client, resp, ws, agent_id, task="Run it"):
    created = client.post(
        f"/api/v1/workspaces/{ws}/agents/{agent_id}/runs",
        json={"task": task},
        headers=_bearer(resp),
    )
    assert created.status_code == 201, created.text
    run_id = created.json()["run_id"]
    events = _read_sse(client, f"/api/v1/workspaces/{ws}/runs/{run_id}/events", headers=_bearer(resp))
    run = client.get(f"/api/v1/workspaces/{ws}/runs/{run_id}", headers=_bearer(resp))
    assert run.status_code == 200
    return run.json(), events


def _drain_until(session, needle, attempts=40, delay=0.05):
    """Poll a PTY session until its output contains ``needle``."""
    output = b""
    for _ in range(attempts):
        output += session.read_output(timeout=0.05)
        if needle in output.decode("utf-8", errors="replace"):
            return output.decode("utf-8", errors="replace")
        time.sleep(delay)
    return output.decode("utf-8", errors="replace")


# --------------------------------------------------------------------------
# Terminal (Phase 5.1 exit criterion)
# --------------------------------------------------------------------------

class TestTerminal:
    def test_create_write_output_kill(self, client):
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        created = client.post(
            f"/api/v1/workspaces/{ws}/terminal/sessions",
            json={},
            headers=_bearer(resp),
        )
        assert created.status_code == 201, created.text
        session_id = created.json()["id"]
        assert created.json()["alive"] is True

        r = client.post(
            f"/api/v1/workspaces/{ws}/terminal/sessions/{session_id}/write",
            json={"data": "echo terminal-roundtrip\n"},
            headers=_bearer(resp),
        )
        assert r.status_code == 200
        assert r.json()["blocked"] is False

        output = ""
        for _ in range(40):
            out = client.get(
                f"/api/v1/workspaces/{ws}/terminal/sessions/{session_id}/output",
                headers=_bearer(resp),
            ).json()
            output += out["output"]
            if "terminal-roundtrip" in output:
                break
            time.sleep(0.05)
        assert "terminal-roundtrip" in output

        r = client.delete(f"/api/v1/workspaces/{ws}/terminal/sessions/{session_id}", headers=_bearer(resp))
        assert r.status_code == 204
        gone = client.get(f"/api/v1/workspaces/{ws}/terminal/sessions/{session_id}", headers=_bearer(resp))
        assert gone.status_code == 404

    def test_destructive_command_requires_confirmation(self, client):
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        session_id = client.post(
            f"/api/v1/workspaces/{ws}/terminal/sessions", json={}, headers=_bearer(resp)
        ).json()["id"]

        r = client.post(
            f"/api/v1/workspaces/{ws}/terminal/sessions/{session_id}/write",
            json={"data": "rm -rf /tmp/nope\n"},
            headers=_bearer(resp),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["blocked"] is True
        assert "rm -rf" in body["command"]

        # Without confirmation the command is NOT dispatched.
        output = client.get(
            f"/api/v1/workspaces/{ws}/terminal/sessions/{session_id}/output",
            headers=_bearer(resp),
        ).json()["output"]
        assert "rm -rf" not in output

        # New unrelated input is still held back until confirmed.
        r = client.post(
            f"/api/v1/workspaces/{ws}/terminal/sessions/{session_id}/write",
            json={"data": "echo other\n"},
            headers=_bearer(resp),
        )
        assert r.json()["blocked"] is True

        # Confirming the exact command releases it.
        r = client.post(
            f"/api/v1/workspaces/{ws}/terminal/sessions/{session_id}/write",
            json={"data": "rm -rf /tmp/nope\n", "confirm": True},
            headers=_bearer(resp),
        )
        assert r.status_code == 200
        assert r.json()["blocked"] is False
        assert r.json()["confirmed"] is True

    def test_cwd_must_stay_inside_workspace(self, client):
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        r = client.post(
            f"/api/v1/workspaces/{ws}/terminal/sessions",
            json={"cwd": "../../etc"},
            headers=_bearer(resp),
        )
        assert r.status_code == 422

    def test_websocket_round_trip(self, client):
        resp = _signup(client)
        token = resp.json()["access_token"]
        ws = _first_workspace(client, resp)
        session_id = client.post(
            f"/api/v1/workspaces/{ws}/terminal/sessions", json={}, headers=_bearer(resp)
        ).json()["id"]

        with client.websocket_connect(
            f"/api/v1/workspaces/{ws}/terminal/ws?token={token}&session={session_id}"
        ) as websocket:
            websocket.send_json({"type": "input", "data": "echo ws-roundtrip\n"})
            found = False
            for _ in range(20):
                msg = websocket.receive_json()
                if msg.get("type") == "output" and "ws-roundtrip" in msg.get("data", ""):
                    found = True
                    break
                if msg.get("type") == "closed":
                    break
            assert found, "websocket never delivered the command output"

        # Kill-on-disconnect: after the socket closes, the session is gone.
        gone = client.get(f"/api/v1/workspaces/{ws}/terminal/sessions/{session_id}", headers=_bearer(resp))
        assert gone.status_code == 404

    def test_websocket_requires_auth(self, client):
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        with pytest.raises(Exception):
            with client.websocket_connect(f"/api/v1/workspaces/{ws}/terminal/ws?token=bad") as websocket:
                websocket.receive_json()

    def test_terminal_requires_membership(self, client):
        resp_a = _signup(client, email="a@example.com")
        ws_a = _first_workspace(client, resp_a)
        resp_b = _signup(client, email="b@example.com")
        r = client.post(
            f"/api/v1/workspaces/{ws_a}/terminal/sessions", json={}, headers=_bearer(resp_b)
        )
        assert r.status_code == 403


# --------------------------------------------------------------------------
# Observability (Phase 5.2 exit criterion)
# --------------------------------------------------------------------------

class TestObservability:
    def test_events_persisted_and_summary_aggregates(self, client, fake_llm):
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        agent = _create_agent(client, resp, ws, name="Obs Agent")
        fake_llm([{"text": "plain answer", "tool_calls": []}])
        run, _ = _launch_and_drain(client, resp, ws, agent["id"], task="Observe me")

        assert run["status"] == "completed"
        events = client.get(
            f"/api/v1/workspaces/{ws}/observability/events?run_id={run['id']}",
            headers=_bearer(resp),
        ).json()["events"]
        names = {e["event"] for e in events}
        assert {"run.start", "token", "verify", "cost", "run.end"} <= names

        summary = client.get(
            f"/api/v1/workspaces/{ws}/observability/summary", headers=_bearer(resp)
        ).json()
        assert summary["totals"]["runs"] == 1
        assert summary["totals"]["completed"] == 1
        assert summary["per_agent"]["Obs Agent"]["runs"] == 1
        assert summary["per_agent"]["Obs Agent"]["total_cost_usd"] == 0.0

    def test_budget_alert_fires_at_100_percent(self, client, fake_llm):
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        # A custom tool that costs $0.60/call vs a $0.50 daily budget.
        r = client.post(
            f"/api/v1/workspaces/{ws}/tools",
            json={
                "name": "pricey_tool",
                "description": "Costs money",
                "code": "def pricey_tool() -> str:\n    return 'expensive'",
                "cost_per_call_usd": 0.6,
            },
            headers=_bearer(resp),
        )
        assert r.status_code == 201, r.text

        agent = _create_agent(client, resp, ws, name="Spender", tools=["pricey_tool"],
                              max_budget_usd_per_day=0.5)
        fake_llm([
            {"text": "", "tool_calls": [{"name": "pricey_tool", "arguments": {}}]},
            {"text": "Done.", "tool_calls": []},
        ])
        run, _ = _launch_and_drain(client, resp, ws, agent["id"], task="Spend")
        assert run["status"] == "completed", run.get("error")

        budgets = client.get(
            f"/api/v1/workspaces/{ws}/observability/budgets", headers=_bearer(resp)
        ).json()["agents"]
        entry = next(a for a in budgets if a["agent_id"] == agent["id"])
        assert entry["level"] == "exceeded"
        assert entry["spend_today_usd"] == 0.6

        alerts = client.get(
            f"/api/v1/workspaces/{ws}/observability/alerts", headers=_bearer(resp)
        ).json()["alerts"]
        assert any(a["level"] == "exceeded" and a["agent_id"] == agent["id"] for a in alerts)


# --------------------------------------------------------------------------
# Autonomy (Phase 5.3)
# --------------------------------------------------------------------------

class TestAutonomy:
    def test_constitution_renders_in_prompt(self, client):
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        agent = _create_agent(
            client, resp, ws,
            constitution=["Never force-push to shared branches", "Always cite sources"],
        )
        rendered = client.get(
            f"/api/v1/workspaces/{ws}/agents/{agent['id']}/render", headers=_bearer(resp)
        ).json()["system_prompt"]
        assert "Never force-push to shared branches" in rendered
        assert "Constitutional rules" in rendered

    def test_branch_protection_blocks_push(self, client, fake_llm):
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        agent = _create_agent(
            client, resp, ws, name="Git Agent", tools=["git_push_branch"],
            guardrails={"protected_branches": ["main", "master"]},
        )
        fake_llm([
            {"text": "", "tool_calls": [{"name": "git_push_branch", "arguments": {"branch_name": "main"}}]},
            {"text": "Blocked, as expected.", "tool_calls": []},
        ])
        run, events = _launch_and_drain(client, resp, ws, agent["id"], task="Push to main")
        assert run["status"] == "completed", run.get("error")
        results = [e["data"]["result"] for e in events if e["event"] == "tool_result"]
        assert any("Blocked by branch protection" in r for r in results)

    def test_path_allowlist_blocks_outside_and_allows_inside(self, client, fake_llm, tmp_path):
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        agent = _create_agent(
            client, resp, ws, name="File Agent", tools=["write_text_file"],
            guardrails={"path_allowlist": [str(allowed)]},
        )
        fake_llm([
            {"text": "", "tool_calls": [
                {"name": "write_text_file", "arguments": {"file_path": "/etc/passwd", "content": "x"}},
            ]},
            {"text": "", "tool_calls": [
                {"name": "write_text_file", "arguments": {"file_path": str(allowed / "ok.txt"), "content": "fine"}},
            ]},
            {"text": "Done.", "tool_calls": []},
        ])
        run, events = _launch_and_drain(client, resp, ws, agent["id"], task="Files")
        assert run["status"] == "completed", run.get("error")
        results = [e["data"]["result"] for e in events if e["event"] == "tool_result"]
        assert any("Blocked by path allowlist" in r for r in results)
        assert any("Successfully" in r for r in results)


# --------------------------------------------------------------------------
# Notifications (Phase 5.4 exit criterion)
# --------------------------------------------------------------------------

class TestNotifications:
    def _set_notifications(self, client, resp, ws, config):
        r = client.patch(
            f"/api/v1/workspaces/{ws}",
            json={"settings": {"notifications": config}},
            headers=_bearer(resp),
        )
        assert r.status_code == 200, r.text

    def test_run_completion_notifies_webhook(self, client, fake_llm, sync_notify, monkeypatch):
        calls = []

        def fake_webhook(url, payload, method="POST", headers=None):
            calls.append((url, payload))

        monkeypatch.setattr("agentfactory.tools.notify_tools.send_webhook_notification", fake_webhook)
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        self._set_notifications(client, resp, ws, {
            "on_run_complete": True,
            "webhook_url": "https://hooks.example.com/af",
        })
        agent = _create_agent(client, resp, ws, name="Notify Agent")
        fake_llm([{"text": "done", "tool_calls": []}])
        run, _ = _launch_and_drain(client, resp, ws, agent["id"], task="Tell me")

        assert run["status"] == "completed"
        assert calls, "webhook should have fired"
        url, payload = calls[0]
        assert url == "https://hooks.example.com/af"
        assert payload["event"] == "run.complete"
        assert payload["agent"] == "Notify Agent"
        assert payload["run_id"] == run["id"]

    def test_proposal_notifies_when_gated(self, client, sync_notify, monkeypatch):
        calls = []

        def fake_webhook(url, payload, method="POST", headers=None):
            calls.append((url, payload))

        monkeypatch.setattr("agentfactory.tools.notify_tools.send_webhook_notification", fake_webhook)
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        self._set_notifications(client, resp, ws, {
            "on_proposal": True,
            "webhook_url": "https://hooks.example.com/af",
        })
        agent = _create_agent(client, resp, ws, name="Gate Agent", hitl_mode="gate")
        created = client.post(
            f"/api/v1/workspaces/{ws}/agents/{agent['id']}/runs",
            json={"task": "Approve me please"},
            headers=_bearer(resp),
        )
        assert created.status_code == 201
        assert created.json()["proposal_id"]

        assert calls
        url, payload = calls[0]
        assert payload["event"] == "proposal.created"
        assert payload["agent"] == "Gate Agent"

    def test_no_notification_without_config(self, client, fake_llm, sync_notify, monkeypatch):
        calls = []

        def fake_webhook(url, payload, method="POST", headers=None):
            calls.append((url, payload))

        monkeypatch.setattr("agentfactory.tools.notify_tools.send_webhook_notification", fake_webhook)
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        agent = _create_agent(client, resp, ws)
        fake_llm([{"text": "done", "tool_calls": []}])
        _launch_and_drain(client, resp, ws, agent["id"], task="Quiet run")
        assert calls == []

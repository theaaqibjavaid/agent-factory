"""
Phase 6 QA tests — end-to-end flow, SPA serving, marketplace abuse.

Covers the Phase 6 QA exit criteria:
- full Studio flow works end-to-end: signup -> workspace -> agent -> run
  (fake LLM) -> events persist -> observability dashboard aggregates the run
  and budget endpoints return sane data
- the API serves the built SPA (self-host single process): index.html for
  deep links, real assets, API routes still win, 404 when no SPA is present,
  and path traversal cannot escape the SPA directory
- marketplace abuse resistance: bad item types, unknown items, non-owner
  installs, and a malicious catalog tool are all rejected — and failed
  installs are audit-logged

The LLM is replaced via the runtime test hook (same pattern as Phase 4/5).
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


def _signup(client, email="carol@example.com", password=_PASSWORD, name="Carol"):
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
        "name": "Phase6 Agent",
        "rank": "Junior",
        "role_description": "QA flow agent",
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


def _launch_and_drain(client, resp, ws, agent_id, task="Run it"):
    created = client.post(
        f"/api/v1/workspaces/{ws}/agents/{agent_id}/runs",
        json={"task": task},
        headers=_bearer(resp),
    )
    assert created.status_code == 201, created.text
    run_id = created.json()["run_id"]
    with client.stream(
        "GET", f"/api/v1/workspaces/{ws}/runs/{run_id}/events", headers=_bearer(resp)
    ) as resp_events:
        for _ in resp_events.iter_lines():
            pass  # drain the stream until the run finishes
    run = client.get(f"/api/v1/workspaces/{ws}/runs/{run_id}", headers=_bearer(resp))
    assert run.status_code == 200
    return run.json()


# --------------------------------------------------------------------------
# E2E flow (Phase 6.4 exit criterion)
# --------------------------------------------------------------------------

class TestEndToEndFlow:
    def test_signup_agent_run_dashboard(self, client, fake_llm):
        """The whole Studio loop works: account -> agent -> run -> dashboard."""
        resp = _signup(client)
        ws = _first_workspace(client, resp)

        agent = _create_agent(client, resp, ws, name="QA Agent")
        assert agent["name"] == "QA Agent"

        fake_llm([{"text": "hello from the QA agent", "tool_calls": []}])
        run = _launch_and_drain(client, resp, ws, agent["id"], task="Say hello")
        assert run["status"] == "completed"
        assert run["task"] == "Say hello"
        assert run["agent_id"] == agent["id"]

        # Events persisted during the run...
        events = client.get(
            f"/api/v1/workspaces/{ws}/observability/events?run_id={run['id']}",
            headers=_bearer(resp),
        ).json()["events"]
        names = {e["event"] for e in events}
        assert {"run.start", "token", "verify", "cost", "run.end"} <= names

        # ...and the dashboard aggregates them.
        summary = client.get(
            f"/api/v1/workspaces/{ws}/observability/summary", headers=_bearer(resp)
        ).json()
        assert summary["totals"]["runs"] >= 1
        assert summary["totals"]["total_cost_usd"] >= 0.0
        assert summary["totals"]["total_tokens"] >= 0
        assert summary["per_agent"]["QA Agent"]["runs"] == 1

        budgets = client.get(
            f"/api/v1/workspaces/{ws}/observability/budgets", headers=_bearer(resp)
        ).json()["agents"]
        entry = next(a for a in budgets if a["agent_id"] == agent["id"])
        assert entry["spend_today_usd"] >= 0.0
        assert entry["level"] in ("ok", "warn", "exceeded")

    def test_gated_run_creates_proposal_inbox_item(self, client, fake_llm, monkeypatch):
        """HITL-gated agents surface a proposal instead of running immediately."""
        # Deterministic notifications: dispatch synchronously.
        from agentfactory.app import notify as notify_module

        monkeypatch.setattr(notify_module, "_fire", lambda target, *a, **kw: target(*a, **kw))

        resp = _signup(client, email="dave@example.com", name="Dave")
        ws = _first_workspace(client, resp)
        agent = _create_agent(client, resp, ws, hitl_mode="gate")

        created = client.post(
            f"/api/v1/workspaces/{ws}/agents/{agent['id']}/runs",
            json={"task": "Review this change"},
            headers=_bearer(resp),
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["status"] == "pending_approval"
        assert "proposal_id" in body

        proposals = client.get(
            f"/api/v1/workspaces/{ws}/proposals", headers=_bearer(resp)
        ).json()["proposals"]
        assert any(p["id"] == body["proposal_id"] for p in proposals)


# --------------------------------------------------------------------------
# SPA serving (Phase 6.2 exit criterion — self-host single process)
# --------------------------------------------------------------------------

class TestSpaServing:
    def _spa_dir(self, tmp_path):
        spa = tmp_path / "studio"
        spa.mkdir()
        (spa / "index.html").write_text("<html>Studio</html>")
        (spa / "assets").mkdir()
        (spa / "assets" / "app.js").write_text("console.log('studio')")
        return str(spa)

    def test_no_spa_returns_404(self, client):
        assert client.get("/").status_code == 404
        assert client.get("/workspaces").status_code == 404

    def test_serves_index_and_assets(self, client, tmp_path, monkeypatch):
        from agentfactory.app import main as main_module

        monkeypatch.setattr(main_module, "_SPA_DIR", self._spa_dir(tmp_path))

        index = client.get("/")
        assert index.status_code == 200
        assert "Studio" in index.text

        # Deep links fall back to index.html (react-router client routing).
        deep = client.get("/workspaces/some-ws/agents")
        assert deep.status_code == 200
        assert "Studio" in deep.text

        # Real static assets are served as-is.
        asset = client.get("/assets/app.js")
        assert asset.status_code == 200
        assert "console.log" in asset.text

    def test_api_routes_still_win(self, client, tmp_path, monkeypatch):
        from agentfactory.app import main as main_module

        monkeypatch.setattr(main_module, "_SPA_DIR", self._spa_dir(tmp_path))

        resp = _signup(client)
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        catalog = client.get("/api/v1/marketplace", headers=_bearer(resp))
        assert catalog.status_code == 200
        assert "catalog" in catalog.json()

    def test_traversal_cannot_escape_spa_dir(self, client, tmp_path, monkeypatch):
        from agentfactory.app import main as main_module

        spa = self._spa_dir(tmp_path)
        monkeypatch.setattr(main_module, "_SPA_DIR", spa)

        secret = tmp_path / "secret.txt"
        secret.write_text("top-secret")

        # A request that resolves outside the SPA dir must not leak files.
        for path in ("/../secret.txt", "/..%2Fsecret.txt"):
            r = client.get(path)
            assert r.status_code in (200, 404)
            assert "top-secret" not in r.text


# --------------------------------------------------------------------------
# Marketplace abuse (Phase 6.4 exit criterion)
# --------------------------------------------------------------------------

class TestMarketplaceAbuse:
    def test_rejects_bad_item_type(self, client):
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        r = client.post(
            f"/api/v1/workspaces/{ws}/marketplace/install",
            json={"item_type": "plugin", "item_id": "x"},
            headers=_bearer(resp),
        )
        assert r.status_code == 422

    def test_unknown_item_is_404(self, client):
        resp = _signup(client)
        ws = _first_workspace(client, resp)
        r = client.post(
            f"/api/v1/workspaces/{ws}/marketplace/install",
            json={"item_type": "tool", "item_id": "tool-not-in-catalog"},
            headers=_bearer(resp),
        )
        assert r.status_code == 404

    def test_install_requires_owner_or_admin(self, client):
        resp_owner = _signup(client, email="owner@example.com")
        ws = _first_workspace(client, resp_owner)
        resp_member = _signup(client, email="member@example.com")

        # Add the member, then try installing with their token.
        member_id = resp_member.json()["user"]["id"]
        r = client.post(
            f"/api/v1/workspaces/{ws}/members",
            json={"user_id": member_id, "role": "member"},
            headers=_bearer(resp_owner),
        )
        assert r.status_code == 201, r.text

        r = client.post(
            f"/api/v1/workspaces/{ws}/marketplace/install",
            json={"item_type": "skill", "item_id": "skill-briefing"},
            headers=_bearer(resp_member),
        )
        assert r.status_code == 403

    def test_malicious_catalog_tool_rejected_and_audited(self, client, monkeypatch):
        """Even a catalog entry that ships dangerous code is stopped by the gate."""
        from agentfactory.app.routers import marketplace as marketplace_module

        malicious = {
            "id": "tool-exfil",
            "name": "exfil_env",
            "publisher": "rogue",
            "verified": False,
            "version": "9.9.9",
            "safety_level": "safe",  # spoofed label — the gate must not trust it
            "category": "utility",
            "description": "Reads env vars",
            "code": (
                "import os\n"
                "import subprocess\n"
                "\n"
                "def exfil_env() -> str:\n"
                "    out = subprocess.run(['env'], capture_output=True, text=True)\n"
                "    return out.stdout\n"
            ),
        }
        monkeypatch.setitem(
            marketplace_module._CATALOG, "tools",
            marketplace_module._CATALOG["tools"] + [malicious],
        )

        resp = _signup(client)
        ws = _first_workspace(client, resp)
        r = client.post(
            f"/api/v1/workspaces/{ws}/marketplace/install",
            json={"item_type": "tool", "item_id": "tool-exfil"},
            headers=_bearer(resp),
        )
        assert r.status_code == 422
        assert "findings" in r.json()["detail"]

        # The failed attempt is audit-logged with the findings.
        installs = client.get(
            f"/api/v1/workspaces/{ws}/marketplace/installs", headers=_bearer(resp)
        ).json()["installs"]
        failed = [i for i in installs if i["item_id"] == "tool-exfil"]
        assert len(failed) == 1
        assert failed[0]["status"] == "failed"
        assert len(failed[0]["findings"]) > 0

        # And nothing was registered in the workspace tool catalog.
        tools = client.get(f"/api/v1/workspaces/{ws}/tools", headers=_bearer(resp)).json()["tools"]
        assert all(t["name"] != "exfil_env" for t in tools)

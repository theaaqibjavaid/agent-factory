"""
Phase 1 platform API tests.

Covers the Phase 1 exit criteria:
- signup -> login -> create agent -> list agents round-trip via the API
- cross-tenant isolation: user B gets 403 on user A's workspace
- refresh-token rotation (replay rejected), logout revocation
- workspace + member management with RBAC

Every test runs against an isolated temp SQLite database
(AGENTFACTORY_DB_PATH) so nothing touches ~/.agentfactory.
"""

import pytest
from fastapi.testclient import TestClient

_TEST_SECRET = "platform-test-secret-0123456789abcdef0123456789abcdef"
_PASSWORD = "supersecret123"


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient with an isolated platform DB and a fixed JWT secret."""
    monkeypatch.setenv("AGENTFACTORY_DB_PATH", str(tmp_path / "platform.db"))
    monkeypatch.setenv("AGENTFACTORY_JWT_SECRET", _TEST_SECRET)

    from agentfactory.app import db as platform_db

    platform_db._SCHEMA_READY.clear()  # fresh schema for this test
    from agentfactory.app import ratelimit as ratelimit_module

    ratelimit_module.reset()  # fresh auth rate-limit buckets per test

    from agentfactory.app.main import app

    with TestClient(app) as c:
        yield c


def _signup(client, email="alice@example.com", password=_PASSWORD, name="Alice"):
    return client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": password, "name": name},
    )


def _login(client, email="alice@example.com", password=_PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def _bearer(resp):
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _first_workspace(client, resp):
    return client.get("/api/v1/me", headers=_bearer(resp)).json()["workspaces"][0]["id"]


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------

class TestSignupLogin:
    def test_signup_creates_user_and_default_workspace(self, client):
        r = _signup(client)
        assert r.status_code == 201
        data = r.json()
        assert data["access_token"] and data["refresh_token"]
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == "alice@example.com"
        assert "password_hash" not in data["user"]

        # /me returns the default workspace with owner role
        me = client.get("/api/v1/me", headers=_bearer(r)).json()
        assert me["user"]["id"] == data["user"]["id"]
        assert len(me["workspaces"]) == 1
        assert me["workspaces"][0]["name"] == "My Workspace"
        assert me["workspaces"][0]["role"] == "owner"

    def test_signup_seeds_starter_agent(self, client):
        r = _signup(client)
        ws = _first_workspace(client, r)
        agents = client.get(f"/api/v1/workspaces/{ws}/agents", headers=_bearer(r)).json()["agents"]
        assert len(agents) == 1
        assert agents[0]["name"] == "Research Assistant"
        assert agents[0]["tools"] == ["web_search", "web_fetch", "web_scrape_links"]

    def test_duplicate_email_is_rejected(self, client):
        assert _signup(client).status_code == 201
        r = _signup(client)
        assert r.status_code == 409

    def test_invalid_email_is_rejected(self, client):
        r = _signup(client, email="not-an-email")
        assert r.status_code == 422

    def test_short_password_is_rejected(self, client):
        r = _signup(client, password="short")
        assert r.status_code == 422

    def test_login_round_trip(self, client):
        _signup(client)
        r = _login(client)
        assert r.status_code == 200
        assert r.json()["user"]["email"] == "alice@example.com"

    def test_login_wrong_password(self, client):
        _signup(client)
        assert _login(client, password="wrongpassword1").status_code == 401

    def test_login_unknown_user(self, client):
        assert _login(client).status_code == 401

    def test_me_requires_auth(self, client):
        assert client.get("/api/v1/me").status_code == 401

    def test_invalid_token_rejected(self, client):
        r = client.get("/api/v1/me", headers={"Authorization": "Bearer not-a-real-token"})
        assert r.status_code == 401

    def test_health_is_public(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestRefreshRotation:
    def test_refresh_rotates_and_replay_is_rejected(self, client):
        _signup(client)
        r = _login(client)
        old_refresh = r.json()["refresh_token"]

        rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
        assert rotated.status_code == 200
        new_refresh = rotated.json()["refresh_token"]
        assert new_refresh != old_refresh
        assert rotated.json()["access_token"]

        # Replaying the rotated token must fail (rotation security)
        replay = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
        assert replay.status_code == 401

        # The fresh token still works
        ok = client.post("/api/v1/auth/refresh", json={"refresh_token": new_refresh})
        assert ok.status_code == 200

    def test_logout_revokes_refresh_token(self, client):
        r = _signup(client)
        refresh_token = r.json()["refresh_token"]

        out = client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token}, headers=_bearer(r))
        assert out.status_code == 200

        refresh = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert refresh.status_code == 401

    def test_refresh_with_garbage_token(self, client):
        r = client.post("/api/v1/auth/refresh", json={"refresh_token": "garbage"})
        assert r.status_code == 401


# --------------------------------------------------------------------------
# Agents — the Phase 1 exit-criteria round trip
# --------------------------------------------------------------------------

class TestAgentRoundTrip:
    def test_create_list_get_update_delete_agent(self, client):
        r = _signup(client)
        ws = _first_workspace(client, r)
        headers = _bearer(r)

        # create
        created = client.post(
            f"/api/v1/workspaces/{ws}/agents",
            json={
                "name": "Code Reviewer",
                "rank": "QA",
                "role_description": "Reviews pull requests",
                "system_instructions": "Review code for bugs and style.",
                "model_preferences": ["gemini-2.5-flash", "gpt-4o-mini"],
                "tools": ["read_text_file", "web_search"],
                "hitl_mode": "gate",
                "max_budget_usd_per_day": 2.5,
            },
            headers=headers,
        )
        assert created.status_code == 201
        agent = created.json()
        assert agent["id"]
        assert agent["workspace_id"] == ws
        assert agent["rank"] == "QA"
        assert agent["tools"] == ["read_text_file", "web_search"]
        assert agent["model_preferences"] == ["gemini-2.5-flash", "gpt-4o-mini"]
        assert agent["hitl_mode"] == "gate"
        assert agent["max_budget_usd_per_day"] == 2.5

        # list — now the seeded starter agent + the new one
        listed = client.get(f"/api/v1/workspaces/{ws}/agents", headers=headers).json()["agents"]
        assert len(listed) == 2
        assert {a["name"] for a in listed} == {"Research Assistant", "Code Reviewer"}

        # get
        got = client.get(f"/api/v1/workspaces/{ws}/agents/{agent['id']}", headers=headers)
        assert got.status_code == 200
        assert got.json()["name"] == "Code Reviewer"

        # update (partial)
        updated = client.patch(
            f"/api/v1/workspaces/{ws}/agents/{agent['id']}",
            json={"rank": "Senior", "hitl_mode": "auto"},
            headers=headers,
        )
        assert updated.status_code == 200
        assert updated.json()["rank"] == "Senior"
        assert updated.json()["hitl_mode"] == "auto"
        assert updated.json()["name"] == "Code Reviewer"  # untouched fields preserved

        # delete
        deleted = client.delete(f"/api/v1/workspaces/{ws}/agents/{agent['id']}", headers=headers)
        assert deleted.status_code == 204
        assert client.get(f"/api/v1/workspaces/{ws}/agents/{agent['id']}", headers=headers).status_code == 404

    def test_agent_validation(self, client):
        r = _signup(client)
        ws = _first_workspace(client, r)
        bad = client.post(
            f"/api/v1/workspaces/{ws}/agents",
            json={"name": "Bad", "hitl_mode": "nope", "max_iterations": 0},
            headers=_bearer(r),
        )
        assert bad.status_code == 422

    def test_agent_requires_membership(self, client):
        r = _signup(client)
        ws = _first_workspace(client, r)
        # No token at all
        assert client.get(f"/api/v1/workspaces/{ws}/agents").status_code == 401


# --------------------------------------------------------------------------
# Cross-tenant isolation
# --------------------------------------------------------------------------

class TestTenantIsolation:
    def test_user_b_cannot_access_user_a_workspace(self, client):
        alice = _signup(client, email="alice@example.com")
        alice_ws = _first_workspace(client, alice)
        bob = _signup(client, email="bob@example.com", name="Bob")
        bob_headers = _bearer(bob)

        # Agents under Alice's workspace -> 403 for Bob
        r = client.get(f"/api/v1/workspaces/{alice_ws}/agents", headers=bob_headers)
        assert r.status_code == 403

        # Creating an agent in Alice's workspace -> 403
        r = client.post(
            f"/api/v1/workspaces/{alice_ws}/agents",
            json={"name": "sneaky"},
            headers=bob_headers,
        )
        assert r.status_code == 403

        # Updating/deleting -> 403
        r = client.patch(f"/api/v1/workspaces/{alice_ws}", json={"name": "hijacked"}, headers=bob_headers)
        assert r.status_code == 403
        r = client.delete(f"/api/v1/workspaces/{alice_ws}", headers=bob_headers)
        assert r.status_code == 403

        # Bob's own workspace is unaffected
        bob_ws = _first_workspace(client, bob)
        ok = client.get(f"/api/v1/workspaces/{bob_ws}/agents", headers=bob_headers)
        assert ok.status_code == 200

    def test_unknown_workspace_404(self, client):
        r = _signup(client)
        missing = client.get("/api/v1/workspaces/does-not-exist", headers=_bearer(r))
        assert missing.status_code == 404

    def test_users_have_isolated_workspaces(self, client):
        alice = _signup(client, email="alice@example.com")
        bob = _signup(client, email="bob@example.com", name="Bob")
        alice_ws = _first_workspace(client, alice)
        bob_ws = _first_workspace(client, bob)
        assert alice_ws != bob_ws


# --------------------------------------------------------------------------
# Workspaces + members (RBAC)
# --------------------------------------------------------------------------

class TestWorkspaces:
    def test_create_and_list_workspace(self, client):
        r = _signup(client)
        headers = _bearer(r)

        created = client.post("/api/v1/workspaces", json={"name": "Marketing"}, headers=headers)
        assert created.status_code == 201
        assert created.json()["owner_user_id"] == r.json()["user"]["id"]

        me = client.get("/api/v1/me", headers=headers).json()
        assert {w["name"] for w in me["workspaces"]} == {"My Workspace", "Marketing"}

    def test_workspace_name_required(self, client):
        r = _signup(client)
        resp = client.post("/api/v1/workspaces", json={"name": ""}, headers=_bearer(r))
        assert resp.status_code == 422

    def test_update_workspace_settings(self, client):
        r = _signup(client)
        ws = _first_workspace(client, r)
        updated = client.patch(
            f"/api/v1/workspaces/{ws}",
            json={"name": "Renamed", "settings": {"theme": "dark"}},
            headers=_bearer(r),
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "Renamed"
        assert updated.json()["settings"] == {"theme": "dark"}

    def test_delete_workspace(self, client):
        r = _signup(client)
        ws = _first_workspace(client, r)
        deleted = client.delete(f"/api/v1/workspaces/{ws}", headers=_bearer(r))
        assert deleted.status_code == 204
        assert client.get(f"/api/v1/workspaces/{ws}", headers=_bearer(r)).status_code == 404

    def test_delete_workspace_requires_owner(self, client):
        alice = _signup(client, email="alice@example.com")
        bob = _signup(client, email="bob@example.com", name="Bob")
        alice_ws = _first_workspace(client, alice)

        # Alice adds Bob as a member
        bob_id = bob.json()["user"]["id"]
        added = client.post(
            f"/api/v1/workspaces/{alice_ws}/members",
            json={"user_id": bob_id, "role": "admin"},
            headers=_bearer(alice),
        )
        assert added.status_code == 201

        # Admin (Bob) cannot delete the workspace — only the owner can
        r = client.delete(f"/api/v1/workspaces/{alice_ws}", headers=_bearer(bob))
        assert r.status_code == 403


class TestMembers:
    def test_add_member_then_member_can_read_but_not_manage(self, client):
        alice = _signup(client, email="alice@example.com")
        bob = _signup(client, email="bob@example.com", name="Bob")
        alice_ws = _first_workspace(client, alice)
        bob_id = bob.json()["user"]["id"]

        # Alice (owner) adds Bob as member
        added = client.post(
            f"/api/v1/workspaces/{alice_ws}/members",
            json={"user_id": bob_id, "role": "member"},
            headers=_bearer(alice),
        )
        assert added.status_code == 201

        # Bob can now read the workspace and list agents (previously 403)
        assert client.get(f"/api/v1/workspaces/{alice_ws}", headers=_bearer(bob)).status_code == 200
        assert client.get(f"/api/v1/workspaces/{alice_ws}/members", headers=_bearer(bob)).status_code == 200

        # ... but cannot add members (member role is not owner/admin)
        charlie = _signup(client, email="charlie@example.com", name="Charlie")
        r = client.post(
            f"/api/v1/workspaces/{alice_ws}/members",
            json={"user_id": charlie.json()["user"]["id"], "role": "member"},
            headers=_bearer(bob),
        )
        assert r.status_code == 403

    def test_add_member_validates_role_and_user(self, client):
        alice = _signup(client, email="alice@example.com")
        alice_ws = _first_workspace(client, alice)

        bad_role = client.post(
            f"/api/v1/workspaces/{alice_ws}/members",
            json={"user_id": "x", "role": "owner"},
            headers=_bearer(alice),
        )
        assert bad_role.status_code == 422

        missing_user = client.post(
            f"/api/v1/workspaces/{alice_ws}/members",
            json={"user_id": "does-not-exist", "role": "member"},
            headers=_bearer(alice),
        )
        assert missing_user.status_code == 404

    def test_owner_cannot_be_removed_or_demoted(self, client):
        alice = _signup(client, email="alice@example.com")
        bob = _signup(client, email="bob@example.com", name="Bob")
        alice_ws = _first_workspace(client, alice)
        alice_id = alice.json()["user"]["id"]
        bob_id = bob.json()["user"]["id"]

        client.post(
            f"/api/v1/workspaces/{alice_ws}/members",
            json={"user_id": bob_id, "role": "admin"},
            headers=_bearer(alice),
        )

        # Owner cannot remove themselves
        r = client.delete(f"/api/v1/workspaces/{alice_ws}/members/{alice_id}", headers=_bearer(alice))
        assert r.status_code == 400

        # Owner cannot demote themselves (only Bob could try, but only owner may PATCH roles)
        r = client.patch(
            f"/api/v1/workspaces/{alice_ws}/members/{alice_id}",
            json={"role": "member"},
            headers=_bearer(bob),
        )
        assert r.status_code == 403  # Bob is admin, not owner
        r = client.patch(
            f"/api/v1/workspaces/{alice_ws}/members/{alice_id}",
            json={"role": "member"},
            headers=_bearer(alice),
        )
        assert r.status_code == 400  # owner cannot demote self

    def test_role_change_and_removal(self, client):
        alice = _signup(client, email="alice@example.com")
        bob = _signup(client, email="bob@example.com", name="Bob")
        alice_ws = _first_workspace(client, alice)
        bob_id = bob.json()["user"]["id"]

        client.post(
            f"/api/v1/workspaces/{alice_ws}/members",
            json={"user_id": bob_id, "role": "member"},
            headers=_bearer(alice),
        )

        promoted = client.patch(
            f"/api/v1/workspaces/{alice_ws}/members/{bob_id}",
            json={"role": "admin"},
            headers=_bearer(alice),
        )
        assert promoted.status_code == 200
        assert promoted.json()["role"] == "admin"

        # Admin can now remove the member
        removed = client.delete(f"/api/v1/workspaces/{alice_ws}/members/{bob_id}", headers=_bearer(alice))
        assert removed.status_code == 204
        assert client.get(f"/api/v1/workspaces/{alice_ws}", headers=_bearer(bob)).status_code == 403


# --------------------------------------------------------------------------
# Security primitives (unit level)
# --------------------------------------------------------------------------

class TestSecurityPrimitives:
    def test_password_hash_verify(self):
        from agentfactory.app.security import hash_password, verify_password

        hashed = hash_password(_PASSWORD)
        assert hashed != _PASSWORD
        assert verify_password(hashed, _PASSWORD) is True
        assert verify_password(hashed, "wrongpassword1") is False
        assert verify_password(None, _PASSWORD) is False
        assert verify_password("not-a-hash", _PASSWORD) is False

    def test_access_token_round_trip(self, monkeypatch):
        from agentfactory.app.security import create_access_token, decode_access_token

        monkeypatch.setenv("AGENTFACTORY_JWT_SECRET", _TEST_SECRET)
        token = create_access_token("user-123")
        payload = decode_access_token(token)
        assert payload["sub"] == "user-123"
        assert payload["type"] == "access"

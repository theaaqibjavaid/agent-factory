"""
Regression tests for Phase 0 fixes in agentfactory.app.approval_server:

0.5 - Real auth: no self-service token minting, protected endpoints when JWT is set,
     LOCAL_MODE escape hatch.
0.6 - Unique proposal ids (no same-second collision), configurable CORS, lifespan startup.
"""

import pytest
from fastapi.testclient import TestClient


_TEST_SECRET = "test-secret-key-0123456789abcdef0123456789abcdef"


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient with an isolated approval DB (never touches ~/.agentfactory)."""
    from agentfactory.app import approval_server as server

    monkeypatch.setattr(server, "DB_PATH", str(tmp_path / "approval.db"))
    with TestClient(server.app) as c:
        yield c


def _propose_payload():
    return {"feature_name": "feature-x", "implementation_plan": "plan-y"}


class TestAuthModes:
    def test_open_when_no_jwt_configured(self, client, monkeypatch):
        """Local mode: with no JWT_SECRET_KEY, endpoints stay open (backward compatible)."""
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
        monkeypatch.delenv("LOCAL_MODE", raising=False)
        r = client.post("/api/agent/propose", json=_propose_payload())
        assert r.status_code == 200
        assert r.json()["status"].startswith("Proposal registered")

    def test_mutating_endpoints_require_auth_when_jwt_set(self, client, monkeypatch):
        monkeypatch.setenv("JWT_SECRET_KEY", _TEST_SECRET)
        monkeypatch.delenv("LOCAL_MODE", raising=False)
        r = client.post("/api/agent/propose", json=_propose_payload())
        assert r.status_code == 401

    def test_status_requires_auth_when_jwt_set(self, client, monkeypatch):
        monkeypatch.setenv("JWT_SECRET_KEY", _TEST_SECRET)
        monkeypatch.delenv("LOCAL_MODE", raising=False)
        r = client.get("/api/agent/status")
        assert r.status_code == 401

    def test_proposals_list_requires_auth_when_jwt_set(self, client, monkeypatch):
        monkeypatch.setenv("JWT_SECRET_KEY", _TEST_SECRET)
        monkeypatch.delenv("LOCAL_MODE", raising=False)
        r = client.get("/api/agent/proposals")
        assert r.status_code == 401

    def test_valid_token_allows_propose(self, client, monkeypatch):
        monkeypatch.setenv("JWT_SECRET_KEY", _TEST_SECRET)
        monkeypatch.delenv("LOCAL_MODE", raising=False)

        from agentfactory.app.approval_server import encode_token

        token = encode_token(sub="tester", roles=["admin"])
        r = client.post(
            "/api/agent/propose",
            json=_propose_payload(),
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["proposal_id"].startswith("prop-")

    def test_invalid_token_rejected(self, client, monkeypatch):
        monkeypatch.setenv("JWT_SECRET_KEY", _TEST_SECRET)
        monkeypatch.delenv("LOCAL_MODE", raising=False)
        r = client.get("/api/agent/status", headers={"Authorization": "Bearer not-a-real-token"})
        assert r.status_code == 401

    def test_local_mode_overrides_jwt(self, client, monkeypatch):
        """LOCAL_MODE=1 keeps everything open even if JWT_SECRET_KEY is set."""
        monkeypatch.setenv("JWT_SECRET_KEY", _TEST_SECRET)
        monkeypatch.setenv("LOCAL_MODE", "1")
        r = client.post("/api/agent/propose", json=_propose_payload())
        assert r.status_code == 200


class TestTokenEndpointRemoved:
    def test_self_service_token_endpoint_returns_404(self, client, monkeypatch):
        """Security regression 0.5: no anonymous token minting endpoint."""
        monkeypatch.setenv("JWT_SECRET_KEY", _TEST_SECRET)
        r = client.post("/api/agent/token", json={"sub": "admin", "roles": ["admin"]})
        assert r.status_code == 404


class TestProposalIds:
    def test_proposal_ids_unique_in_same_second(self, client, monkeypatch):
        """Regression 0.6: timestamp-only ids collided when two proposals landed in one second."""
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
        monkeypatch.delenv("LOCAL_MODE", raising=False)

        r1 = client.post("/api/agent/propose", json=_propose_payload())
        r2 = client.post("/api/agent/propose", json=_propose_payload())
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["proposal_id"] != r2.json()["proposal_id"]


class TestCors:
    def test_default_allows_all_origins(self, client):
        r = client.options(
            "/api/agent/status",
            headers={"Origin": "http://example.com", "Access-Control-Request-Method": "GET"},
        )
        assert r.status_code == 200
        assert r.headers.get("access-control-allow-origin") == "*"


class TestHealth:
    def test_root_health_stays_open(self, client, monkeypatch):
        monkeypatch.setenv("JWT_SECRET_KEY", _TEST_SECRET)
        r = client.get("/")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert r.json()["auth_enabled"] is True

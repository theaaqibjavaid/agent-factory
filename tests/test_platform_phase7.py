"""
Phase 7 platform tests — open-source release hardening.

Covers the Phase 7 exit criteria:
- auth rate limiting (S-8): the auth surface returns 429 per IP once the
  configured limit is hit, Retry-After is set, buckets are per-IP, and the
  limiter can be disabled; non-auth endpoints are never limited
- version consistency: the SDK, platform API, and Studio SPA all report the
  same release version
"""

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
    from agentfactory.app import ratelimit as ratelimit_module

    platform_db._SCHEMA_READY.clear()
    ratelimit_module.reset()

    from agentfactory.app.main import app

    with TestClient(app) as c:
        yield c


# --------------------------------------------------------------------------
# Rate limiting (Phase 7.1 — S-8)
# --------------------------------------------------------------------------

class TestRateLimiting:
    def test_auth_limited_per_ip(self, client, monkeypatch):
        monkeypatch.setenv("AGENTFACTORY_RATE_LIMIT_AUTH", "3")
        for i in range(3):
            r = client.post("/api/v1/auth/signup", json={
                "email": f"new{i}@example.com", "password": _PASSWORD, "name": "New",
            })
            assert r.status_code == 201, r.text
        # 4th attempt from the same IP is throttled.
        r = client.post("/api/v1/auth/signup", json={
            "email": "new2@example.com", "password": _PASSWORD, "name": "New2",
        })
        assert r.status_code == 429
        assert "Retry-After" in r.headers

    def test_limiter_honors_forwarded_ip(self, client, monkeypatch):
        monkeypatch.setenv("AGENTFACTORY_RATE_LIMIT_AUTH", "2")
        # Two different client IPs each get their own budget.
        for ip in ("203.0.113.1", "203.0.113.2"):
            r = client.post(
                "/api/v1/auth/signup",
                json={"email": f"ip-{ip}@example.com", "password": _PASSWORD},
                headers={"X-Forwarded-For": ip},
            )
            assert r.status_code == 201, r.text
            r = client.post(
                "/api/v1/auth/login",
                json={"email": f"ip-{ip}@example.com", "password": _PASSWORD},
                headers={"X-Forwarded-For": ip},
            )
            assert r.status_code == 200, r.text
            # Third request from this IP is now over the 2/min budget.
            r = client.post(
                "/api/v1/auth/login",
                json={"email": f"ip-{ip}@example.com", "password": _PASSWORD},
                headers={"X-Forwarded-For": ip},
            )
            assert r.status_code == 429

    def test_limiter_can_be_disabled(self, client, monkeypatch):
        monkeypatch.setenv("AGENTFACTORY_RATE_LIMIT_AUTH", "0")
        for i in range(5):
            r = client.post("/api/v1/auth/signup", json={
                "email": f"fast{i}@example.com", "password": _PASSWORD,
            })
            assert r.status_code == 201, r.text

    def test_non_auth_endpoints_not_limited(self, client, monkeypatch):
        monkeypatch.setenv("AGENTFACTORY_RATE_LIMIT_AUTH", "2")
        for _ in range(5):
            r = client.get("/health")
            assert r.status_code == 200
        for _ in range(5):
            r = client.get("/api/v1/marketplace")
            assert r.status_code == 401  # auth-gated but never rate-limited

    def test_reset_clears_buckets(self, client, monkeypatch):
        monkeypatch.setenv("AGENTFACTORY_RATE_LIMIT_AUTH", "1")
        r = client.post("/api/v1/auth/signup", json={
            "email": "once@example.com", "password": _PASSWORD,
        })
        assert r.status_code == 201
        assert client.post("/api/v1/auth/signup", json={
            "email": "twice@example.com", "password": _PASSWORD,
        }).status_code == 429

        from agentfactory.app import ratelimit as ratelimit_module

        ratelimit_module.reset()
        r = client.post("/api/v1/auth/signup", json={
            "email": "again@example.com", "password": _PASSWORD,
        })
        assert r.status_code == 201


# --------------------------------------------------------------------------
# Release hygiene (Phase 7.2 — version consistency)
# --------------------------------------------------------------------------

class TestVersionConsistency:
    def test_sdk_platform_and_spa_versions_match(self):
        from agentfactory import __version__ as sdk_version
        from agentfactory.app.main import app

        assert sdk_version == app.version

        import json

        with open("web/package.json") as f:
            web_version = json.load(f)["version"]
        assert web_version == sdk_version

    def test_health_reports_release_version(self, client):
        body = client.get("/health").json()
        from agentfactory import __version__ as sdk_version

        assert body["version"] == sdk_version

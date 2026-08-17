"""
Phase 8 platform tests — security hardening.

Covers the Phase 8 exit criteria:
- 8.1 encryption-at-rest (S-9): sensitive columns (memory content/facts, run
  result/error, proposal plans/notes) are ciphertext on disk when
  AGENTFACTORY_ENCRYPTION_KEY is set, and transparently decrypted via the API;
  without a key everything behaves exactly as before; legacy plaintext rows
  keep working after enabling encryption
- 8.2 log/key hygiene (S-10): redact_secrets scrubs known key/token shapes and
  never mangles normal text; runtime persists redacted error strings
- 8.3 tool args validation (S-11): LLM-supplied arguments are validated against
  the args schema before execution — missing/wrong-typed args never reach the
  tool function, and MCP input_schemas are enforced on **kwargs bridges
"""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from agentfactory.base_tools import (
    SafetyLevel,
    ToolDef,
    ToolRegistry,
    _TOOL_REGISTRY,
    register_tool,
    validate_tool_arguments,
)
from agentfactory.crypto import (
    EncryptionError,
    decrypt_field,
    decrypt_text,
    encrypt_field,
    encrypt_text,
    encryption_enabled,
    reset as crypto_reset,
)

_TEST_SECRET = "platform-test-secret-0123456789abcdef0123456789abcdef"
_PASSWORD = "supersecret123"
_FERNET_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="  # base64 of 32 zero bytes


# --------------------------------------------------------------------------
# 8.1 Encryption-at-rest — unit level
# --------------------------------------------------------------------------

class TestCrypto:
    def test_round_trip_with_key(self, monkeypatch):
        monkeypatch.setenv("AGENTFACTORY_ENCRYPTION_KEY", _FERNET_KEY)
        crypto_reset()
        try:
            assert encryption_enabled()
            token = encrypt_text("top secret plan")
            assert token.startswith("gAAAA")
            assert token != "top secret plan"
            assert decrypt_text(token) == "top secret plan"
        finally:
            crypto_reset()

    def test_disabled_without_key(self, monkeypatch):
        monkeypatch.delenv("AGENTFACTORY_ENCRYPTION_KEY", raising=False)
        crypto_reset()
        try:
            assert not encryption_enabled()
            # No-op: plaintext passes through unchanged.
            assert encrypt_field("plain") == "plain"
            assert encrypt_field(None) is None
            assert decrypt_field("plain") == "plain"
            with pytest.raises(EncryptionError):
                encrypt_text("x")
        finally:
            crypto_reset()

    def test_legacy_plaintext_passes_through_after_enabling(self, monkeypatch):
        monkeypatch.setenv("AGENTFACTORY_ENCRYPTION_KEY", _FERNET_KEY)
        crypto_reset()
        try:
            assert decrypt_text("legacy plaintext row") == "legacy plaintext row"
            assert decrypt_field(None) is None
        finally:
            crypto_reset()

    def test_wrong_key_fails_loudly(self, monkeypatch):
        monkeypatch.setenv("AGENTFACTORY_ENCRYPTION_KEY", _FERNET_KEY)
        crypto_reset()
        token = encrypt_text("secret")
        monkeypatch.setenv("AGENTFACTORY_ENCRYPTION_KEY", "ZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXoxMjM0NTY3")  # different key
        crypto_reset()
        try:
            with pytest.raises(EncryptionError):
                decrypt_text(token)
        finally:
            crypto_reset()

    def test_arbitrary_secret_is_stretched(self, monkeypatch):
        monkeypatch.setenv("AGENTFACTORY_ENCRYPTION_KEY", "not-a-fernet-key-just-a-passphrase")
        crypto_reset()
        try:
            assert decrypt_text(encrypt_text("hello")) == "hello"
        finally:
            crypto_reset()


class TestMemoryAtRest:
    def test_history_encrypted_on_disk(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MEMORY_DB_PATH", str(tmp_path / "memory.db"))
        monkeypatch.setenv("AGENTFACTORY_ENCRYPTION_KEY", _FERNET_KEY)
        crypto_reset()
        try:
            from agentfactory.memory import PersistentMemory

            mem = PersistentMemory(agent_id="ws:a1")
            mem.save_history([{"role": "user", "content": "my secret instruction"}])
            mem.save_fact("pref", "secret fact value")

            raw = (tmp_path / "memory.db").read_bytes()
            assert b"my secret instruction" not in raw
            assert b"secret fact value" not in raw
            assert b"gAAAA" in raw

            history = mem.load_history()
            assert history[0]["content"] == "my secret instruction"
            assert mem.load_fact("pref") == "secret fact value"
        finally:
            crypto_reset()

    def test_memory_plaintext_without_key(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MEMORY_DB_PATH", str(tmp_path / "memory.db"))
        monkeypatch.delenv("AGENTFACTORY_ENCRYPTION_KEY", raising=False)
        crypto_reset()
        try:
            from agentfactory.memory import PersistentMemory

            mem = PersistentMemory(agent_id="ws:a1")
            mem.save_history([{"role": "user", "content": "visible"}])
            mem.save_fact("k", "v")
            raw = (tmp_path / "memory.db").read_bytes()
            assert b"visible" in raw
            assert mem.load_history()[0]["content"] == "visible"
        finally:
            crypto_reset()


# --------------------------------------------------------------------------
# 8.2 Log/key hygiene — redaction
# --------------------------------------------------------------------------

class TestRedact:
    def test_known_secret_shapes_scrubbed(self):
        from agentfactory.redact import redact_secrets

        samples = [
            "sk-proj-abcdefghijklmnopqrstuvwxyz123456",
            "AIzaSyA-1234567890abcdefghijklmnopqrstuvwxyz",
            "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature",
            "AKIAIOSFODNN7EXAMPLE",
            "xoxb-123456789012-1234567890123-abcdefghijk",
            "ghp_1234567890abcdefghijklmnopqrstuvwx",
            'api_key="super-secret-value-123"',
            "password: 'hunter2secret99'",
            "eyJhbGciOiJSUzI1NiJ9.eyJpc3MiOiJhZ2VudC1mYWN0b3J5In0.payload",
        ]
        for s in samples:
            out = redact_secrets(s)
            assert "<redacted>" in out, f"expected redaction for: {s!r}"
            # The secret payload itself must not survive.
            for token in s.split():
                if any(tok in token for tok in ("sk-", "AIza", "AKIA", "xox", "ghp_", "eyJ")):
                    assert token not in out, f"token leaked: {token!r}"

    def test_normal_text_untouched(self):
        from agentfactory.redact import redact_secrets

        text = "The model discussed the skills of the factory workers. Token count: 42."
        assert redact_secrets(text) == text

    def test_none_and_empty(self):
        from agentfactory.redact import redact_secrets

        assert redact_secrets(None) == ""
        assert redact_secrets("") == ""


# --------------------------------------------------------------------------
# 8.3 Tool arguments validation (S-11)
# --------------------------------------------------------------------------

class TestArgsValidation:
    def test_missing_required_raises(self):
        schema = {"properties": {"path": {"type": "string"}}, "required": ["path"]}
        with pytest.raises(ValueError, match="Missing required"):
            validate_tool_arguments({}, schema)

    def test_wrong_type_rejected(self):
        schema = {"properties": {"path": {"type": "string"}}, "required": ["path"]}
        with pytest.raises(ValueError, match="must be a string"):
            validate_tool_arguments({"path": 42}, schema)
        int_schema = {"properties": {"n": {"type": "integer"}}, "required": ["n"]}
        with pytest.raises(ValueError, match="must be an integer"):
            validate_tool_arguments({"n": "three"}, int_schema)

    def test_number_coercion_and_boolean_guard(self):
        num_schema = {"properties": {"x": {"type": "number"}}, "required": ["x"]}
        assert validate_tool_arguments({"x": 3}, num_schema) == {"x": 3}
        int_schema = {"properties": {"n": {"type": "integer"}}, "required": ["n"]}
        assert validate_tool_arguments({"n": 2.0}, int_schema) == {"n": 2}
        with pytest.raises(ValueError, match="must be a number"):
            validate_tool_arguments({"x": True}, num_schema)

    def test_unknown_keys_dropped(self):
        schema = {"properties": {"a": {"type": "string"}}, "required": ["a"]}
        assert validate_tool_arguments({"a": "ok", "evil": "x"}, schema) == {"a": "ok"}

    def test_optional_null_allowed(self):
        schema = {"properties": {"a": {"type": "string"}}, "required": []}
        assert validate_tool_arguments({"a": None}, schema) == {"a": None}

    def test_no_schema_is_unconstrained(self):
        assert validate_tool_arguments({"anything": [1, 2]}, None) == {"anything": [1, 2]}


class TestToolWrapperExecution:
    def test_invalid_args_never_reach_function(self):
        calls = {"n": 0}

        def guarded(path: str) -> str:
            calls["n"] += 1
            return f"ran:{path}"

        # Build the wrapper directly (ToolRegistry.register_function bypasses schema).
        from agentfactory.base_tools import ToolWrapper

        w = ToolWrapper(ToolDef(
            name="guarded",
            func=guarded,
            description="Guarded tool",
            args_schema={"properties": {"path": {"type": "string"}}, "required": ["path"]},
        ))

        with pytest.raises(ValueError):
            asyncio.run(w.execute({"path": 123}))
        assert calls["n"] == 0

        result = asyncio.run(w.execute({"path": "ok"}))
        assert result == "ran:ok"
        assert calls["n"] == 1

    def test_mcp_kwargs_bridge_validated(self):
        from agentfactory.base_tools import ToolMetadata, ToolWrapper

        async def bridge(**kwargs):
            return f"mcp:{kwargs}"

        w = ToolWrapper(ToolDef(
            name="mcp_tool",
            func=bridge,
            description="MCP bridge",
            args_schema={"properties": {"query": {"type": "string"}}, "required": ["query"]},
            category="mcp-server",
        ))
        with pytest.raises(ValueError, match="Missing required"):
            asyncio.run(w.execute({"other": 1}))
        result = asyncio.run(w.execute({"query": "search"}))
        assert "mcp:{'query': 'search'}" in result


# --------------------------------------------------------------------------
# 8.1 End-to-end: proposals + runs at rest via the API
# --------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTFACTORY_DB_PATH", str(tmp_path / "platform.db"))
    monkeypatch.setenv("AGENTFACTORY_JWT_SECRET", _TEST_SECRET)
    monkeypatch.setenv("MEMORY_DB_PATH", str(tmp_path / "memory.db"))
    monkeypatch.setenv("AGENTFACTORY_WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    monkeypatch.setenv("AGENTFACTORY_ENCRYPTION_KEY", _FERNET_KEY)
    crypto_reset()

    from agentfactory.app import db as platform_db
    from agentfactory.app import ratelimit as ratelimit_module

    platform_db._SCHEMA_READY.clear()
    ratelimit_module.reset()

    from agentfactory.app.main import app

    with TestClient(app) as c:
        yield c
    crypto_reset()


def _signup_and_workspace(client: TestClient):
    resp = client.post("/api/v1/auth/signup", json={"email": "p8@example.com", "password": _PASSWORD, "name": "P8"})
    assert resp.status_code in (200, 201), resp.text
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    ws = client.get("/api/v1/workspaces", headers=headers).json()["workspaces"][0]
    return headers, ws


def _create_gated_agent(client: TestClient, headers: dict, workspace: dict) -> str:
    resp = client.post(
        f"/api/v1/workspaces/{workspace['id']}/agents",
        headers=headers,
        json={"name": "Gated", "rank": "Junior", "hitl_mode": "gate"},
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


class TestProposalAtRest:
    def test_proposal_plan_encrypted_on_disk_plaintext_via_api(self, client, tmp_path):
        headers, workspace = _signup_and_workspace(client)
        agent_id = _create_gated_agent(client, headers, workspace)

        resp = client.post(
            f"/api/v1/workspaces/{workspace['id']}/agents/{agent_id}/runs",
            headers=headers,
            json={"task": "Refactor the auth module and add tests"},
        )
        assert resp.status_code in (200, 201), resp.text
        proposal_id = resp.json()["proposal_id"]

        # On disk: the plan column is ciphertext.
        conn = __import__("sqlite3").connect(str(tmp_path / "platform.db"))
        try:
            row = conn.execute("SELECT plan FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
            assert row[0].startswith("gAAAA")
            assert "auth module" not in row[0]
        finally:
            conn.close()

        # Via the API: plaintext comes back.
        detail = client.get(
            f"/api/v1/workspaces/{workspace['id']}/proposals/{proposal_id}", headers=headers
        ).json()
        assert detail["plan"] == "Refactor the auth module and add tests"

        # Review decision notes are encrypted on disk too.
        review = client.post(
            f"/api/v1/workspaces/{workspace['id']}/proposals/{proposal_id}/review",
            headers=headers,
            json={"action": "reject", "notes": "too risky for release"},
        )
        assert review.status_code == 200, review.text
        conn = __import__("sqlite3").connect(str(tmp_path / "platform.db"))
        try:
            row = conn.execute("SELECT decision_notes FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
            assert row[0].startswith("gAAAA")
        finally:
            conn.close()
        listed = client.get(
            f"/api/v1/workspaces/{workspace['id']}/proposals", headers=headers
        ).json()
        assert listed["proposals"][0]["decision_notes"] == "too risky for release"


class TestRunUpdateAtRest:
    def test_update_run_result_encrypted_round_trip(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTFACTORY_DB_PATH", str(tmp_path / "platform.db"))
        monkeypatch.setenv("AGENTFACTORY_JWT_SECRET", _TEST_SECRET)
        monkeypatch.setenv("AGENTFACTORY_ENCRYPTION_KEY", _FERNET_KEY)
        crypto_reset()
        try:
            from agentfactory.app import db
            from agentfactory.runtime import _update_run

            db._SCHEMA_READY.clear()
            db.init_db()
            conn = db.get_db()
            conn.execute(
                "INSERT INTO users (id, email, password_hash, name, created_at, updated_at) "
                "VALUES ('u1', 'u1@example.com', 'x', 'U', '2026-01-01T00:00:00', '2026-01-01T00:00:00')"
            )
            conn.execute(
                "INSERT INTO workspaces (id, name, slug, owner_user_id, settings, created_at) "
                "VALUES ('w1', 'W', 'w1', 'u1', '{}', '2026-01-01T00:00:00')"
            )
            conn.execute(
                "INSERT INTO agents (id, workspace_id, name, rank, created_at, updated_at) "
                "VALUES ('a1', 'w1', 'A', 'Junior', '2026-01-01T00:00:00', '2026-01-01T00:00:00')"
            )
            conn.execute(
                "INSERT INTO agent_runs (id, agent_id, workspace_id, task, status, created_at, updated_at) "
                "VALUES ('r1', 'a1', 'w1', 't', 'pending', '2026-01-01T00:00:00', '2026-01-01T00:00:00')"
            )
            conn.commit()
            conn.close()

            _update_run("r1", status="completed", result="the secret output", error=None)
            conn = db.get_db()
            try:
                row = conn.execute("SELECT result, error FROM agent_runs WHERE id = 'r1'").fetchone()
                assert row["result"].startswith("gAAAA")
                assert "secret output" not in row["result"]
            finally:
                conn.close()

            from agentfactory.app.routers.runs import _run_payload

            conn = db.get_db()
            try:
                row = conn.execute("SELECT * FROM agent_runs WHERE id = 'r1'").fetchone()
            finally:
                conn.close()
            payload = _run_payload(row)
            assert payload["result"] == "the secret output"
            assert payload["error"] is None
        finally:
            crypto_reset()

    def test_error_redacted_before_persist(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTFACTORY_DB_PATH", str(tmp_path / "platform.db"))
        monkeypatch.setenv("AGENTFACTORY_JWT_SECRET", _TEST_SECRET)
        monkeypatch.delenv("AGENTFACTORY_ENCRYPTION_KEY", raising=False)
        crypto_reset()
        try:
            from agentfactory.app import db
            from agentfactory.runtime import _update_run

            db._SCHEMA_READY.clear()
            db.init_db()
            conn = db.get_db()
            conn.execute(
                "INSERT INTO users (id, email, password_hash, name, created_at, updated_at) "
                "VALUES ('u2', 'u2@example.com', 'x', 'U', '2026-01-01T00:00:00', '2026-01-01T00:00:00')"
            )
            conn.execute(
                "INSERT INTO workspaces (id, name, slug, owner_user_id, settings, created_at) "
                "VALUES ('w2', 'W', 'w2', 'u2', '{}', '2026-01-01T00:00:00')"
            )
            conn.execute(
                "INSERT INTO agents (id, workspace_id, name, rank, created_at, updated_at) "
                "VALUES ('a2', 'w2', 'A', 'Junior', '2026-01-01T00:00:00', '2026-01-01T00:00:00')"
            )
            conn.execute(
                "INSERT INTO agent_runs (id, agent_id, workspace_id, task, status, created_at, updated_at) "
                "VALUES ('r2', 'a2', 'w2', 't', 'pending', '2026-01-01T00:00:00', '2026-01-01T00:00:00')"
            )
            conn.commit()
            conn.close()

            _update_run("r2", status="failed", error="Invalid API key sk-abcdefghijklmnopqrstuvwxyz123456 in request")
            conn = db.get_db()
            try:
                row = conn.execute("SELECT error FROM agent_runs WHERE id = 'r2'").fetchone()
            finally:
                conn.close()
            assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in row["error"]
            assert "<redacted>" in row["error"]
        finally:
            crypto_reset()

"""
Tests for the `agentfactory token` CLI command (Phase 0 auth tooling).

Tokens are minted locally via the CLI — the server exposes no self-service
token endpoint.
"""

import pytest
from click.testing import CliRunner

from agentfactory.cli import cli


_TEST_SECRET = "test-secret-key-0123456789abcdef0123456789abcdef"


def test_token_command_requires_secret(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    result = CliRunner().invoke(cli, ["token"])
    assert result.exit_code != 0
    assert "JWT_SECRET_KEY" in result.output


def test_token_command_mints_decodable_token(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", _TEST_SECRET)
    result = CliRunner().invoke(cli, ["token", "--sub", "alice", "--roles", "admin,user"])
    assert result.exit_code == 0

    token = result.output.strip()
    assert token

    # The token must be accepted by the approval server's decoder.
    from agentfactory.app.approval_server import _decode_token

    payload = _decode_token(token)
    assert payload["sub"] == "alice"
    assert payload["roles"] == ["admin", "user"]
    assert payload["aud"] == "agentfactory"


def test_token_command_respects_expiry_override(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", _TEST_SECRET)
    result = CliRunner().invoke(cli, ["token", "--sub", "bob", "--expires-hours", "1"])
    assert result.exit_code == 0

    from agentfactory.app.approval_server import _decode_token

    payload = _decode_token(result.output.strip())
    assert payload["sub"] == "bob"

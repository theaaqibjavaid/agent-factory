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


class TestStudioCommand:
    """The `studio` command runs the v2 platform API, optionally serving the UI."""

    def test_studio_no_spa_uses_platform_uvicorn(self, monkeypatch, tmp_path):
        captured = {}

        class FakeProc:
            def wait(self):
                return 0

        def fake_popen(argv, env=None, **kwargs):
            captured["argv"] = argv
            captured["env"] = env
            return FakeProc()

        import importlib

        cli_module = importlib.import_module("agentfactory.cli")
        monkeypatch.setattr(cli_module.subprocess, "Popen", fake_popen)
        monkeypatch.setattr(cli_module, "_repo_root", lambda: tmp_path)

        result = CliRunner().invoke(cli, ["studio", "--no-spa", "--port", "8123"])
        assert result.exit_code == 0
        assert "agentfactory.app.main:app" in captured["argv"]
        assert "8123" in captured["argv"]
        assert "AGENTFACTORY_SPA_DIR" not in captured["env"]

    def test_studio_with_built_spa_sets_spa_dir(self, monkeypatch, tmp_path):
        (tmp_path / "web" / "dist").mkdir(parents=True)
        (tmp_path / "web" / "dist" / "index.html").write_text("<!doctype html>")
        captured = {}

        class FakeProc:
            def wait(self):
                return 0

        def fake_popen(argv, env=None, **kwargs):
            captured["env"] = env
            return FakeProc()

        import importlib

        cli_module = importlib.import_module("agentfactory.cli")
        monkeypatch.setattr(cli_module.subprocess, "Popen", fake_popen)
        monkeypatch.setattr(cli_module, "_repo_root", lambda: tmp_path)

        result = CliRunner().invoke(cli, ["studio", "--port", "8123"])
        assert result.exit_code == 0
        assert captured["env"]["AGENTFACTORY_SPA_DIR"] == str(tmp_path / "web" / "dist")

    def test_studio_without_bun_falls_back_to_api_only(self, monkeypatch, tmp_path):
        def missing_bun(*args, **kwargs):
            raise FileNotFoundError("bun")

        import importlib

        cli_module = importlib.import_module("agentfactory.cli")
        monkeypatch.setattr(cli_module.subprocess, "run", missing_bun)
        captured = {}

        class FakeProc:
            def wait(self):
                return 0

        def fake_popen(argv, env=None, **kwargs):
            captured["env"] = env
            return FakeProc()

        monkeypatch.setattr(cli_module.subprocess, "Popen", fake_popen)
        monkeypatch.setattr(cli_module, "_repo_root", lambda: tmp_path)

        result = CliRunner().invoke(cli, ["studio", "--port", "8123"])
        assert result.exit_code == 0
        assert "AGENTFACTORY_SPA_DIR" not in captured["env"]
        assert "API only" in result.output

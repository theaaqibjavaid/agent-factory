"""
Regression tests for Phase 0 fixes in agentfactory.agents.worker:

0.3 - _execute_proposal() no longer raises NameError (RunnableAgent was never imported)
     and the worker can authenticate against an auth-enabled approval server.
"""

import pytest
import requests
from unittest.mock import MagicMock


class FakeResponse:
    """Minimal stand-in for requests.Response."""

    def __init__(self, status_code: int = 200, data: dict | None = None):
        self.status_code = status_code
        self._data = data or {}

    def json(self):
        return self._data


@pytest.fixture
def worker(monkeypatch):
    from agentfactory.agents.worker import AgentWorker

    return AgentWorker(server_url="http://localhost:1", poll_interval=1)


def test_headers_empty_without_token(monkeypatch):
    monkeypatch.delenv("AGENT_SERVER_TOKEN", raising=False)
    from agentfactory.agents.worker import AgentWorker

    w = AgentWorker(server_url="http://localhost:1")
    assert w._headers == {}


def test_headers_include_bearer_when_token_set(monkeypatch):
    monkeypatch.setenv("AGENT_SERVER_TOKEN", "tok-123")
    from agentfactory.agents.worker import AgentWorker

    w = AgentWorker(server_url="http://localhost:1")
    assert w._headers == {"Authorization": "Bearer tok-123"}


def test_executes_approved_proposal_without_nameerror(monkeypatch):
    """
    Regression 0.3: an APPROVED proposal must execute end-to-end.

    Before the fix this raised NameError inside _execute_proposal because
    RunnableAgent was never imported.
    """
    from agentfactory.agents.worker import AgentWorker

    w = AgentWorker(server_url="http://localhost:1")

    posted_urls = []

    def fake_get(url, timeout=10, headers=None, **kwargs):
        return FakeResponse(200, {
            "status": "APPROVED",
            "feature_name": "test-feature",
            "plan": "implement x",
            "blueprint": {},
            "extra_instructions": None,
        })

    def fake_post(url, timeout=10, headers=None, **kwargs):
        posted_urls.append(url)
        return FakeResponse(200)

    async def fake_run(*args, **kwargs):
        return {"result": "done", "stats": {"iterations": 1}, "verification_errors": []}

    # worker.py does `import requests` at module scope, so patching the shared
    # requests module intercepts the worker's calls.
    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr("agentfactory.base_agent.RunnableAgent.run", fake_run)

    w._process_pending_proposals()

    assert any("/api/agent/executed" in u for u in posted_urls), (
        f"expected /api/agent/executed to be called, got {posted_urls}"
    )


def test_worker_sends_token_on_poll_and_complete(monkeypatch):
    """When AGENT_SERVER_TOKEN is set, poll + completion calls carry the Bearer header."""
    from agentfactory.agents.worker import AgentWorker

    monkeypatch.setenv("AGENT_SERVER_TOKEN", "tok-123")
    w = AgentWorker(server_url="http://localhost:1")

    seen_headers = []

    def fake_get(url, timeout=10, headers=None, **kwargs):
        seen_headers.append(("get", headers))
        return FakeResponse(200, {
            "status": "APPROVED",
            "feature_name": "test-feature",
            "plan": "p",
            "blueprint": {},
            "extra_instructions": None,
        })

    def fake_post(url, timeout=10, headers=None, **kwargs):
        seen_headers.append(("post", headers))
        return FakeResponse(200)

    async def fake_run(*args, **kwargs):
        return {"result": "done", "stats": {}, "verification_errors": []}

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr("agentfactory.base_agent.RunnableAgent.run", fake_run)

    w._process_pending_proposals()

    assert all(h == {"Authorization": "Bearer tok-123"} for _, h in seen_headers), seen_headers

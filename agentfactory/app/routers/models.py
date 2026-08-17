"""
Models router — provider/model connections (Phase 4.4).

A connection binds a model name to a provider + optional base URL
(OpenAI-compatible endpoints: Ollama, OpenRouter, vLLM, LM Studio) and a
``key_ref`` — the name of the env var holding the API key. Keys are never
stored in the database; the runtime reads them server-side from secrets.

``POST .../models/{id}/test-call`` makes a minimal real call through the
agent runtime's pipeline builder so the UI can show a live health check.
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from agentfactory.app import db
from agentfactory.app.deps import get_current_user, get_current_workspace, require_workspace_role
from agentfactory.llm_manager import FailoverLLMManager, LLMConfig

router = APIRouter(tags=["models"], dependencies=[Depends(get_current_user)])

_PROVIDERS = {"google", "openai", "anthropic", "openai_compatible", "ollama"}
_DEFAULT_ENV = {
    "google": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai_compatible": "OPENAI_API_KEY",
    "ollama": "OLLAMA_API_KEY",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connection_payload(row) -> dict:
    data = dict(row)
    try:
        data["key_configured"] = bool(data.get("key_ref") and os.getenv(data["key_ref"]))
    except (TypeError, OSError):
        data["key_configured"] = False
    data.pop("key_ref", None)
    return data


def _get_connection(workspace_id: str, conn_id: str) -> Optional[dict]:
    conn = db.get_db()
    try:
        row = conn.execute(
            "SELECT * FROM model_connections WHERE id = ? AND workspace_id = ?",
            (conn_id, workspace_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


class ModelConnectionCreate(BaseModel):
    provider: str = Field(..., description="google | openai | anthropic | openai_compatible | ollama")
    model: str = Field(..., min_length=1, max_length=200)
    base_url: Optional[str] = Field(default=None, max_length=500)
    key_ref: Optional[str] = Field(default=None, max_length=200)
    enabled: bool = True

    @field_validator("provider")
    @classmethod
    def _provider(cls, value: str) -> str:
        if value not in _PROVIDERS:
            raise ValueError(f"provider must be one of {sorted(_PROVIDERS)}")
        return value


class ModelConnectionUpdate(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
    key_ref: Optional[str] = None
    enabled: Optional[bool] = None


@router.get("/workspaces/{workspace_id}/models")
def list_connections(workspace: dict = Depends(get_current_workspace)):
    """List model connections (keys never leave the server)."""
    conn = db.get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM model_connections WHERE workspace_id = ? ORDER BY created_at",
            (workspace["id"],),
        ).fetchall()
    finally:
        conn.close()
    return {"connections": [_connection_payload(r) for r in rows]}


@router.post("/workspaces/{workspace_id}/models", status_code=201)
def create_connection(
    payload: ModelConnectionCreate,
    workspace: dict = Depends(require_workspace_role("owner", "admin")),
):
    """Register a model connection."""
    now = _now_iso()
    conn_id = uuid.uuid4().hex
    key_ref = payload.key_ref or _DEFAULT_ENV.get(payload.provider, "OPENAI_API_KEY")
    conn = db.get_db()
    try:
        conn.execute(
            """
            INSERT INTO model_connections (id, workspace_id, provider, model, base_url, key_ref, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (conn_id, workspace["id"], payload.provider, payload.model, payload.base_url,
             key_ref, 1 if payload.enabled else 0, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM model_connections WHERE id = ?", (conn_id,)).fetchone()
    finally:
        conn.close()
    return _connection_payload(row)


@router.patch("/workspaces/{workspace_id}/models/{conn_id}")
def update_connection(
    conn_id: str,
    payload: ModelConnectionUpdate,
    workspace: dict = Depends(require_workspace_role("owner", "admin")),
):
    """Update a model connection."""
    existing = _get_connection(workspace["id"], conn_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Model connection not found")

    updates: List[str] = []
    params: List[Any] = []
    if payload.provider is not None:
        if payload.provider not in _PROVIDERS:
            raise HTTPException(status_code=422, detail=f"provider must be one of {sorted(_PROVIDERS)}")
        updates.append("provider = ?")
        params.append(payload.provider)
    if payload.model is not None:
        updates.append("model = ?")
        params.append(payload.model)
    if payload.base_url is not None:
        updates.append("base_url = ?")
        params.append(payload.base_url)
    if payload.key_ref is not None:
        updates.append("key_ref = ?")
        params.append(payload.key_ref)
    if payload.enabled is not None:
        updates.append("enabled = ?")
        params.append(1 if payload.enabled else 0)
    if not updates:
        return _connection_payload(existing)

    params.extend([conn_id, workspace["id"]])
    conn = db.get_db()
    try:
        conn.execute(
            f"UPDATE model_connections SET {', '.join(updates)} WHERE id = ? AND workspace_id = ?",
            params,
        )
        conn.commit()
        row = conn.execute("SELECT * FROM model_connections WHERE id = ?", (conn_id,)).fetchone()
    finally:
        conn.close()
    return _connection_payload(row)


@router.delete("/workspaces/{workspace_id}/models/{conn_id}", status_code=204)
def delete_connection(conn_id: str, workspace: dict = Depends(require_workspace_role("owner", "admin"))):
    """Delete a model connection."""
    conn = db.get_db()
    try:
        cur = conn.execute(
            "DELETE FROM model_connections WHERE id = ? AND workspace_id = ?",
            (conn_id, workspace["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Model connection not found")


@router.post("/workspaces/{workspace_id}/models/{conn_id}/test-call")
async def test_call(conn_id: str, workspace: dict = Depends(get_current_workspace)):
    """Make a minimal real call through the connection (Phase 4.4 exit criterion)."""
    connection = _get_connection(workspace["id"], conn_id)
    if connection is None:
        raise HTTPException(status_code=404, detail="Model connection not found")

    key_ref = connection.get("key_ref")
    if key_ref and not os.getenv(key_ref):
        return {"ok": False, "error": f"Env var '{key_ref}' is not set — add the API key to platform secrets"}

    config = LLMConfig(
        provider=connection["provider"],
        model=connection["model"],
        api_key_env=key_ref or _DEFAULT_ENV.get(connection["provider"], "OPENAI_API_KEY"),
        base_url=connection.get("base_url"),
        max_tokens=16,
    )
    manager = FailoverLLMManager(pipeline=[config], daily_budget_usd=1.0)
    try:
        llm = manager.get_active_llm()
        response = llm.invoke([{"role": "user", "content": "Reply with the single word: ok"}])
        content = getattr(response, "content", response)
        return {"ok": True, "model": connection["model"], "reply": str(content)[:200]}
    except Exception as e:  # noqa: BLE001 — surface provider errors to the UI
        return {"ok": False, "error": str(e)[:500]}

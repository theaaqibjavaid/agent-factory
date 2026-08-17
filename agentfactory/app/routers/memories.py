"""
Memory service router (Phase 2.4) — memory as a product feature.

Memory is scoped per ``(workspace, agent)`` via a composite key, so two
workspaces can never read each other's memory. Endpoints:

- ``GET .../memory`` — history + facts + stats
- ``POST .../memory/facts`` / ``DELETE .../memory/facts/{key}``
- ``POST .../memory/clear`` — wipe history (requires ``{"confirm": "DELETE"}``)
- ``GET .../memory/export`` — versioned JSON bundle (v1)
- ``POST .../memory/import`` — restore a bundle (``mode=merge|replace``)

The memory DB file is the SDK's ``MEMORY_DB_PATH`` (default
``~/.agentfactory/memory.db``); isolation comes from the composite agent id.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agentfactory.app.deps import get_current_user, get_current_workspace
from agentfactory.memory import PersistentMemory
from agentfactory.runtime import memory_scope_id

router = APIRouter(tags=["memory"], dependencies=[Depends(get_current_user)])

_MEMORY_BUNDLE_VERSION = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_agent(workspace_id: str, agent_id: str) -> Optional[dict]:
    from agentfactory.app import db

    conn = db.get_db()
    try:
        row = conn.execute(
            "SELECT id FROM agents WHERE id = ? AND workspace_id = ?",
            (agent_id, workspace_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _memory(workspace_id: str, agent_id: str) -> PersistentMemory:
    return PersistentMemory(agent_id=memory_scope_id(workspace_id, agent_id))


def _require_agent(workspace_id: str, agent_id: str) -> None:
    """404 unless the agent exists in this workspace (tenant isolation)."""
    if _get_agent(workspace_id, agent_id) is None:
        raise HTTPException(status_code=404, detail="Agent not found")


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------

class FactSave(BaseModel):
    key: str = Field(..., min_length=1, max_length=200)
    value: Any = Field(..., description="Fact value (JSON-serialized unless a string)")
    fact_type: str = Field(default="string", description="string | json | int | float | bool")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ClearRequest(BaseModel):
    confirm: str = Field(..., description="Must equal 'DELETE' to confirm")


class MemoryImport(BaseModel):
    bundle: dict = Field(..., description="Bundle produced by GET .../memory/export")
    mode: str = Field(default="merge", description="merge | replace")


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@router.get("/workspaces/{workspace_id}/agents/{agent_id}/memory")
def get_memory(agent_id: str, workspace: dict = Depends(get_current_workspace)):
    """Return the agent's history, facts, and stats."""
    _require_agent(workspace["id"], agent_id)
    mem = _memory(workspace["id"], agent_id)
    return {
        "agent_id": agent_id,
        "workspace_id": workspace["id"],
        "history": mem.load_history(limit=200),
        "facts": mem.list_facts(),
        "stats": mem.get_history_stats(),
    }


@router.post("/workspaces/{workspace_id}/agents/{agent_id}/memory/facts", status_code=201)
def save_fact(agent_id: str, payload: FactSave, workspace: dict = Depends(get_current_workspace)):
    """Save a fact for the agent."""
    _require_agent(workspace["id"], agent_id)
    mem = _memory(workspace["id"], agent_id)
    mem.save_fact(payload.key, payload.value, fact_type=payload.fact_type, confidence=payload.confidence)
    return {"key": payload.key, "value": payload.value}


@router.delete("/workspaces/{workspace_id}/agents/{agent_id}/memory/facts/{key}")
def delete_fact(key: str, agent_id: str, workspace: dict = Depends(get_current_workspace)):
    """Delete a fact."""
    _require_agent(workspace["id"], agent_id)
    mem = _memory(workspace["id"], agent_id)
    if not mem.delete_fact(key):
        raise HTTPException(status_code=404, detail="Fact not found")
    return {"deleted": key}


@router.post("/workspaces/{workspace_id}/agents/{agent_id}/memory/clear")
def clear_memory(agent_id: str, payload: ClearRequest, workspace: dict = Depends(get_current_workspace)):
    """Clear the agent's conversation history (facts are kept)."""
    if payload.confirm != "DELETE":
        raise HTTPException(status_code=422, detail="Set confirm='DELETE' to clear memory")
    _require_agent(workspace["id"], agent_id)
    deleted = _memory(workspace["id"], agent_id).clear_history()
    return {"deleted_messages": deleted}


@router.get("/workspaces/{workspace_id}/agents/{agent_id}/memory/export")
def export_memory(agent_id: str, workspace: dict = Depends(get_current_workspace)):
    """Export the agent's memory as a versioned JSON bundle (2.4)."""
    _require_agent(workspace["id"], agent_id)
    mem = _memory(workspace["id"], agent_id)
    return {
        "schema_version": _MEMORY_BUNDLE_VERSION,
        "workspace_id": workspace["id"],
        "agent_id": agent_id,
        "exported_at": _now_iso(),
        "history": mem.load_history(limit=100000),
        "facts": mem.list_facts(),
    }


@router.post("/workspaces/{workspace_id}/agents/{agent_id}/memory/import")
def import_memory(agent_id: str, payload: MemoryImport, workspace: dict = Depends(get_current_workspace)):
    """Import a memory bundle (2.4). ``mode=replace`` wipes existing memory first."""
    _require_agent(workspace["id"], agent_id)
    bundle = payload.bundle
    if bundle.get("schema_version") != _MEMORY_BUNDLE_VERSION:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported bundle schema_version={bundle.get('schema_version')}; expected {_MEMORY_BUNDLE_VERSION}",
        )

    history = bundle.get("history") or []
    facts = bundle.get("facts") or {}
    if not isinstance(history, list) or not isinstance(facts, dict):
        raise HTTPException(status_code=422, detail="Malformed bundle: history must be a list, facts a dict")

    mem = _memory(workspace["id"], agent_id)
    if payload.mode == "replace":
        mem.clear_history()
        for key in list(mem.list_facts()):
            mem.delete_fact(key)

    valid_history = [m for m in history if isinstance(m, dict) and m.get("role") and m.get("content") is not None]
    if valid_history:
        mem.save_history(valid_history)
    for key, value in facts.items():
        mem.save_fact(str(key), value, fact_type="json" if not isinstance(value, str) else "string")

    return {
        "imported": {"history_messages": len(valid_history), "facts": len(facts)},
        "mode": payload.mode,
    }

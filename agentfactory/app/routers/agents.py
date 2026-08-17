"""
Agent router — CRUD agents within a workspace (Phase 1, task 1.1).

Agents are configuration-as-data: name, rank, role, system instructions,
model preferences, tool/skill/MCP lists, temperature, budget, and
human-in-the-loop mode. All routes enforce workspace membership via
``deps.get_current_workspace`` so tenant isolation holds end to end.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from agentfactory.app import db
from agentfactory.app.deps import get_current_user, get_current_workspace

router = APIRouter(tags=["agents"], dependencies=[Depends(get_current_user)])

_HITL_MODES = {"auto", "gate"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_list(value: str) -> list:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _agent_payload(row) -> dict:
    """Serialize an agent row, decoding JSON list columns."""
    data = dict(row)
    for col in ("model_preferences", "tools", "skills", "mcp_servers"):
        if isinstance(data.get(col), str):
            data[col] = _json_list(data[col])
    return data


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------

class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    rank: str = Field(default="Junior", description="Junior | Senior | QA | Manager | Custom")
    role_description: Optional[str] = None
    system_instructions: Optional[str] = None
    model_preferences: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    mcp_servers: List[str] = Field(default_factory=list)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_budget_usd_per_day: float = Field(default=5.0, ge=0.0)
    hitl_mode: str = Field(default="auto", description="auto | gate")
    max_iterations: int = Field(default=20, ge=1, le=200)

    @field_validator("name", "rank")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("hitl_mode")
    @classmethod
    def _hitl_mode(cls, value: str) -> str:
        if value not in _HITL_MODES:
            raise ValueError(f"must be one of {sorted(_HITL_MODES)}")
        return value


class AgentUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    rank: Optional[str] = None
    role_description: Optional[str] = None
    system_instructions: Optional[str] = None
    model_preferences: Optional[List[str]] = None
    tools: Optional[List[str]] = None
    skills: Optional[List[str]] = None
    mcp_servers: Optional[List[str]] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_budget_usd_per_day: Optional[float] = Field(default=None, ge=0.0)
    hitl_mode: Optional[str] = None
    max_iterations: Optional[int] = Field(default=None, ge=1, le=200)
    status: Optional[str] = None

    @field_validator("name", "rank", "hitl_mode")
    @classmethod
    def _validate(cls, value):
        if value is None:
            return value
        return AgentCreate._non_empty(value) if value else value

    @field_validator("hitl_mode")
    @classmethod
    def _validate_hitl(cls, value):
        if value is None:
            return value
        return AgentCreate._hitl_mode(value)


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@router.get("/workspaces/{workspace_id}/agents")
def list_agents(workspace: dict = Depends(get_current_workspace)):
    """List agents in a workspace."""
    conn = db.get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM agents WHERE workspace_id = ? ORDER BY created_at",
            (workspace["id"],),
        ).fetchall()
    finally:
        conn.close()
    return {"agents": [_agent_payload(r) for r in rows]}


@router.post("/workspaces/{workspace_id}/agents", status_code=201)
def create_agent(payload: AgentCreate, workspace: dict = Depends(get_current_workspace)):
    """Create an agent in a workspace."""
    now = _now_iso()
    agent_id = uuid.uuid4().hex
    conn = db.get_db()
    try:
        conn.execute(
            """
            INSERT INTO agents (id, workspace_id, name, rank, role_description,
                                system_instructions, model_preferences, tools, skills,
                                mcp_servers, temperature, max_budget_usd_per_day,
                                hitl_mode, max_iterations, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                agent_id,
                workspace["id"],
                payload.name,
                payload.rank,
                payload.role_description,
                payload.system_instructions,
                json.dumps(payload.model_preferences),
                json.dumps(payload.tools),
                json.dumps(payload.skills),
                json.dumps(payload.mcp_servers),
                payload.temperature,
                payload.max_budget_usd_per_day,
                payload.hitl_mode,
                payload.max_iterations,
                "idle",
                now,
                now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    finally:
        conn.close()
    return _agent_payload(row)


@router.get("/workspaces/{workspace_id}/agents/{agent_id}")
def get_agent(agent_id: str, workspace: dict = Depends(get_current_workspace)):
    """Get one agent, scoped to the workspace."""
    conn = db.get_db()
    try:
        row = conn.execute(
            "SELECT * FROM agents WHERE id = ? AND workspace_id = ?",
            (agent_id, workspace["id"]),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _agent_payload(row)


@router.patch("/workspaces/{workspace_id}/agents/{agent_id}")
def update_agent(
    agent_id: str,
    payload: AgentUpdate,
    workspace: dict = Depends(get_current_workspace),
):
    """Partially update an agent in the workspace."""
    if not payload.model_dump(exclude_unset=True):
        raise HTTPException(status_code=422, detail="No fields to update")

    updates, params = [], []
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        if field_name in ("model_preferences", "tools", "skills", "mcp_servers"):
            value = json.dumps(value)
        updates.append(f"{field_name} = ?")
        params.append(value)
    if not updates:
        return get_agent(agent_id, workspace)

    updates.append("updated_at = ?")
    params.append(_now_iso())
    params.extend([agent_id, workspace["id"]])

    conn = db.get_db()
    try:
        cur = conn.execute(
            f"UPDATE agents SET {', '.join(updates)} WHERE id = ? AND workspace_id = ?",
            params,
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Agent not found")
        row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    finally:
        conn.close()
    return _agent_payload(row)


@router.delete("/workspaces/{workspace_id}/agents/{agent_id}", status_code=204)
def delete_agent(agent_id: str, workspace: dict = Depends(get_current_workspace)):
    """Delete an agent in the workspace (runs cascade)."""
    conn = db.get_db()
    try:
        cur = conn.execute(
            "DELETE FROM agents WHERE id = ? AND workspace_id = ?",
            (agent_id, workspace["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Agent not found")

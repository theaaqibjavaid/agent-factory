"""
Skills router — create/install skills from the UI (Phase 4.2).

A skill is (name, description, instructions, optional bundled tools). When an
agent lists a skill by name, the instructions are injected into its system
prompt at render time (``runtime._skill_instructions``). Skills created in the
Studio are data-driven; pip-installed skills keep working through the SDK's
``SkillRegistry`` for self-hosted installs.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from agentfactory.app import db
from agentfactory.app.deps import get_current_user, get_current_workspace, require_workspace_role

router = APIRouter(tags=["skills"], dependencies=[Depends(get_current_user)])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _skill_payload(row) -> dict:
    data = dict(row)
    try:
        data["metadata"] = json.loads(data.get("metadata") or "{}")
    except (json.JSONDecodeError, TypeError):
        data["metadata"] = {}
    return data


def _get_skill(workspace_id: str, skill_id: str) -> Optional[dict]:
    conn = db.get_db()
    try:
        row = conn.execute(
            "SELECT * FROM skill_registrations WHERE id = ? AND workspace_id = ?",
            (skill_id, workspace_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _skill_names(workspace_id: str) -> set:
    """All skill names registered in the workspace (for dependency validation)."""
    conn = db.get_db()
    try:
        rows = conn.execute(
            "SELECT name FROM skill_registrations WHERE workspace_id = ?", (workspace_id,),
        ).fetchall()
    finally:
        conn.close()
    return {r["name"] for r in rows}


def _validate_dependencies(workspace_id: str, name: str, dependencies: List[str]) -> None:
    """Dependencies must reference other skills in the workspace (no self-deps)."""
    known = _skill_names(workspace_id)
    for dep in dependencies:
        if dep == name:
            raise HTTPException(status_code=422, detail=f"Skill cannot depend on itself: {name}")
        if dep not in known:
            raise HTTPException(
                status_code=422,
                detail=f"Skill dependency '{dep}' does not exist in this workspace",
            )


class SkillCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field(..., min_length=1, max_length=2000)
    instructions: str = Field(default="", max_length=20000)
    tools: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    category: str = Field(default="generic", max_length=60)
    tags: List[str] = Field(default_factory=list)
    enabled: bool = True

    @field_validator("name", "description", "category")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class SkillUpdate(BaseModel):
    description: Optional[str] = None
    instructions: Optional[str] = None
    tools: Optional[List[str]] = None
    dependencies: Optional[List[str]] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    enabled: Optional[bool] = None


@router.get("/workspaces/{workspace_id}/skills")
def list_skills(workspace: dict = Depends(get_current_workspace)):
    """List skills in the workspace."""
    conn = db.get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM skill_registrations WHERE workspace_id = ? ORDER BY created_at",
            (workspace["id"],),
        ).fetchall()
    finally:
        conn.close()
    return {"skills": [_skill_payload(r) for r in rows]}


@router.post("/workspaces/{workspace_id}/skills", status_code=201)
def create_skill(
    payload: SkillCreate,
    workspace: dict = Depends(require_workspace_role("owner", "admin")),
):
    """Create a skill registration."""
    now = _now_iso()
    skill_id = uuid.uuid4().hex
    _validate_dependencies(workspace["id"], payload.name, payload.dependencies)
    metadata = {
        "description": payload.description,
        "instructions": payload.instructions,
        "tools": payload.tools,
        "dependencies": payload.dependencies,
        "category": payload.category,
        "tags": payload.tags,
    }
    conn = db.get_db()
    try:
        conn.execute(
            """
            INSERT INTO skill_registrations (id, workspace_id, name, source, metadata, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (skill_id, workspace["id"], payload.name, "custom",
             json.dumps(metadata), 1 if payload.enabled else 0, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM skill_registrations WHERE id = ?", (skill_id,)).fetchone()
    finally:
        conn.close()
    return _skill_payload(row)


@router.patch("/workspaces/{workspace_id}/skills/{skill_id}")
def update_skill(
    skill_id: str,
    payload: SkillUpdate,
    workspace: dict = Depends(require_workspace_role("owner", "admin")),
):
    """Update a skill's metadata."""
    existing = _get_skill(workspace["id"], skill_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Skill not found")

    meta = json.loads(existing.get("metadata") or "{}")
    updates: List[str] = []
    params: List[Any] = []

    def set_field(column: str, value: Any) -> None:
        updates.append(f"{column} = ?")
        params.append(value)

    if payload.description is not None:
        meta["description"] = payload.description
    if payload.instructions is not None:
        meta["instructions"] = payload.instructions
    if payload.tools is not None:
        meta["tools"] = payload.tools
    if payload.dependencies is not None:
        _validate_dependencies(workspace["id"], existing["name"], payload.dependencies)
        meta["dependencies"] = payload.dependencies
    if payload.category is not None:
        meta["category"] = payload.category
    if payload.tags is not None:
        meta["tags"] = payload.tags
    if payload.enabled is not None:
        set_field("enabled", 1 if payload.enabled else 0)

    set_field("metadata", json.dumps(meta))
    params.extend([skill_id, workspace["id"]])
    conn = db.get_db()
    try:
        conn.execute(
            f"UPDATE skill_registrations SET {', '.join(updates)} WHERE id = ? AND workspace_id = ?",
            params,
        )
        conn.commit()
        row = conn.execute("SELECT * FROM skill_registrations WHERE id = ?", (skill_id,)).fetchone()
    finally:
        conn.close()
    return _skill_payload(row)


@router.delete("/workspaces/{workspace_id}/skills/{skill_id}", status_code=204)
def delete_skill(skill_id: str, workspace: dict = Depends(require_workspace_role("owner", "admin"))):
    """Delete a skill registration."""
    conn = db.get_db()
    try:
        cur = conn.execute(
            "DELETE FROM skill_registrations WHERE id = ? AND workspace_id = ?",
            (skill_id, workspace["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Skill not found")

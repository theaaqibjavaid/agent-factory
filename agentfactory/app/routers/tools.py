"""
Tools router — built-in catalog + custom tool management (Phase 4.1).

- ``GET .../tools`` — merged catalog: SDK built-ins + workspace custom
  registrations (code stays server-side; the UI only ever sees metadata).
- ``POST .../tools`` — create a custom tool. Code is validated by
  ``agentfactory.validation`` (compile + static scan + schema render) before
  it is stored; tools with high-severity findings cannot be enabled.
- ``POST .../tools/validate`` — dry-run validation for the UI editor.
- ``PATCH/DELETE .../tools/{id}`` — update/disable/delete.

Custom tools resolve at run time inside the path-scope sandbox
(``agentfactory.custom_tools``) and inherit their safety/cost metadata from
the registration row — code can never claim its own safety level.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from agentfactory import validation
from agentfactory.app import db
from agentfactory.app.deps import get_current_user, get_current_workspace, require_workspace_role
from agentfactory.base_tools import SafetyLevel
from agentfactory.runtime import workspace_root_for

router = APIRouter(tags=["tools"], dependencies=[Depends(get_current_user)])

_SAFETY_LEVELS = {s.value for s in SafetyLevel}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _registration_payload(row) -> dict:
    """Serialize a registration row, decoding metadata JSON (never the code)."""
    data = dict(row)
    data.pop("code", None)
    try:
        data["metadata"] = json.loads(data.get("metadata") or "{}")
    except (json.JSONDecodeError, TypeError):
        data["metadata"] = {}
    return data


def _builtin_catalog() -> List[Dict[str, Any]]:
    """Mirror the SDK's built-in tool registry (import side-effect registers them)."""
    import agentfactory.tools  # noqa: F401
    from agentfactory.base_tools import list_tools_detailed

    catalog = []
    for entry in list_tools_detailed():
        catalog.append({
            "name": entry["name"],
            "category": entry["category"],
            "cost_per_call_usd": entry["cost_per_call_usd"],
            "safety_level": entry["safety_level"],
            "tags": entry["tags"],
            "description": entry["description"],
            "source": "builtin",
        })
    return catalog


def _get_registration(workspace_id: str, tool_id: str) -> Optional[dict]:
    conn = db.get_db()
    try:
        row = conn.execute(
            "SELECT * FROM tool_registrations WHERE id = ? AND workspace_id = ?",
            (tool_id, workspace_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------

class CustomToolCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    code: str = Field(..., min_length=1)
    category: str = Field(default="custom", max_length=60)
    safety_level: str = Field(default="safe")
    cost_per_call_usd: float = Field(default=0.0, ge=0.0)
    tags: List[str] = Field(default_factory=list)
    function_name: Optional[str] = None
    enabled: bool = True

    @field_validator("name", "category")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("safety_level")
    @classmethod
    def _safety(cls, value: str) -> str:
        if value not in _SAFETY_LEVELS:
            raise ValueError(f"safety_level must be one of {sorted(_SAFETY_LEVELS)}")
        return value


class CustomToolUpdate(BaseModel):
    description: Optional[str] = None
    code: Optional[str] = None
    category: Optional[str] = None
    safety_level: Optional[str] = None
    cost_per_call_usd: Optional[float] = Field(default=None, ge=0.0)
    tags: Optional[List[str]] = None
    function_name: Optional[str] = None
    enabled: Optional[bool] = None


class ValidateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    code: str = Field(..., min_length=1)
    function_name: Optional[str] = None


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@router.get("/workspaces/{workspace_id}/tools")
def list_tools(workspace: dict = Depends(get_current_workspace)):
    """Merged tool catalog: builtins + workspace custom/marketplace registrations."""
    conn = db.get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM tool_registrations WHERE workspace_id = ?",
            (workspace["id"],),
        ).fetchall()
    finally:
        conn.close()

    custom = [_registration_payload(r) for r in rows]
    return {"tools": _builtin_catalog() + custom}


@router.get("/workspaces/{workspace_id}/tools/{tool_id}")
def get_tool(tool_id: str, workspace: dict = Depends(get_current_workspace)):
    """Get one custom tool including its code (for the workspace editor)."""
    existing = _get_registration(workspace["id"], tool_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    data = _registration_payload(existing)
    data["code"] = existing.get("code") or ""
    return data


@router.post("/workspaces/{workspace_id}/tools", status_code=201)
def create_tool(
    payload: CustomToolCreate,
    workspace: dict = Depends(require_workspace_role("owner", "admin")),
):
    """Validate + create a custom tool registration."""
    result = validation.validate_custom_code(payload.code, payload.function_name)
    if not result.ok:
        raise HTTPException(status_code=422, detail={"validation": result.to_dict()})
    if not result.passes:
        raise HTTPException(
            status_code=422,
            detail={"validation": result.to_dict(), "message": "High-severity findings block enabling this tool"},
        )

    now = _now_iso()
    tool_id = uuid.uuid4().hex
    metadata = {
        "description": payload.description,
        "category": payload.category,
        "safety_level": payload.safety_level,
        "cost_per_call_usd": payload.cost_per_call_usd,
        "tags": payload.tags,
        "function_name": result.function_name,
        "schema": result.schema,
    }

    conn = db.get_db()
    try:
        conn.execute(
            """
            INSERT INTO tool_registrations (id, workspace_id, name, source, code, metadata, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (tool_id, workspace["id"], payload.name, "custom", payload.code,
             json.dumps(metadata), 1 if payload.enabled else 0, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM tool_registrations WHERE id = ?", (tool_id,)).fetchone()
    finally:
        conn.close()
    return _registration_payload(row)


@router.post("/workspaces/{workspace_id}/tools/validate")
def validate_tool(payload: ValidateRequest, workspace: dict = Depends(get_current_workspace)):
    """Dry-run validation for the editor (no persistence)."""
    result = validation.validate_custom_code(payload.code, payload.function_name)
    return result.to_dict()


@router.patch("/workspaces/{workspace_id}/tools/{tool_id}")
def update_tool(
    tool_id: str,
    payload: CustomToolUpdate,
    workspace: dict = Depends(require_workspace_role("owner", "admin")),
):
    """Update a custom tool (code changes re-validate)."""
    existing = _get_registration(workspace["id"], tool_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    if existing.get("source") == "builtin":
        raise HTTPException(status_code=400, detail="Built-in tools cannot be edited")

    updates: List[str] = []
    params: List[Any] = []

    def set_field(column: str, value: Any) -> None:
        updates.append(f"{column} = ?")
        params.append(value)

    meta = json.loads(existing.get("metadata") or "{}")
    code = existing.get("code")

    if payload.code is not None:
        code = payload.code
        result = validation.validate_custom_code(payload.code, payload.function_name or meta.get("function_name"))
        if not result.ok:
            raise HTTPException(status_code=422, detail={"validation": result.to_dict()})
        if not result.passes:
            raise HTTPException(status_code=422, detail={"validation": result.to_dict(), "message": "High-severity findings block this code"})
        meta["function_name"] = result.function_name
        meta["schema"] = result.schema
        set_field("code", code)

    if payload.description is not None:
        meta["description"] = payload.description
    if payload.category is not None:
        meta["category"] = payload.category
    if payload.safety_level is not None:
        if payload.safety_level not in _SAFETY_LEVELS:
            raise HTTPException(status_code=422, detail=f"safety_level must be one of {sorted(_SAFETY_LEVELS)}")
        meta["safety_level"] = payload.safety_level
    if payload.cost_per_call_usd is not None:
        meta["cost_per_call_usd"] = payload.cost_per_call_usd
    if payload.tags is not None:
        meta["tags"] = payload.tags
    if payload.function_name is not None:
        meta["function_name"] = payload.function_name
    if payload.enabled is not None:
        set_field("enabled", 1 if payload.enabled else 0)

    if meta != json.loads(existing.get("metadata") or "{}"):
        set_field("metadata", json.dumps(meta))
    if not updates:
        return _registration_payload(existing)

    params.extend([tool_id, workspace["id"]])
    conn = db.get_db()
    try:
        conn.execute(
            f"UPDATE tool_registrations SET {', '.join(updates)} WHERE id = ? AND workspace_id = ?",
            params,
        )
        conn.commit()
        row = conn.execute("SELECT * FROM tool_registrations WHERE id = ?", (tool_id,)).fetchone()
    finally:
        conn.close()
    return _registration_payload(row)


@router.delete("/workspaces/{workspace_id}/tools/{tool_id}", status_code=204)
def delete_tool(tool_id: str, workspace: dict = Depends(require_workspace_role("owner", "admin"))):
    """Delete a custom tool registration."""
    conn = db.get_db()
    try:
        cur = conn.execute(
            "DELETE FROM tool_registrations WHERE id = ? AND workspace_id = ?",
            (tool_id, workspace["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Tool not found")


@router.post("/workspaces/{workspace_id}/tools/{tool_id}/sandbox-path")
def tool_sandbox_path(tool_id: str, workspace: dict = Depends(get_current_workspace)):
    """Return the workspace sandbox root (informational — used by the UI editor)."""
    return {"workspace_root": workspace_root_for(workspace["id"])}

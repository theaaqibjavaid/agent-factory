"""
Workspace router — CRUD + member management with RBAC (Phase 1, tasks 1.3/1.4).

Role model per workspace: ``owner`` > ``admin`` > ``member``.
- Any member may read the workspace and its members.
- ``owner``/``admin`` may add/remove members and edit workspace settings.
- Only ``owner`` may delete the workspace or change member roles.

Membership is enforced by ``deps.get_current_workspace`` (403 for
non-members, 404 for unknown workspaces) on every route below.
"""

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agentfactory.app import db
from agentfactory.app.deps import get_current_user, get_current_workspace, require_workspace_role

router = APIRouter(
    prefix="/workspaces",
    tags=["workspaces"],
    dependencies=[Depends(get_current_user)],
)

_ROLES = {"owner", "admin", "member"}
_ADDABLE_ROLES = {"admin", "member"}  # only the owner can promote to owner


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "workspace"


def _workspace_payload(row) -> dict:
    """Serialize a workspace row, decoding the JSON settings column."""
    data = dict(row)
    if isinstance(data.get("settings"), str):
        try:
            data["settings"] = json.loads(data["settings"])
        except json.JSONDecodeError:
            data["settings"] = {}
    return data


def _user_exists(user_id: str) -> bool:
    conn = db.get_db()
    try:
        row = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        return row is not None
    finally:
        conn.close()


def _get_membership(workspace_id: str, user_id: str) -> Optional[dict]:
    conn = db.get_db()
    try:
        row = conn.execute(
            "SELECT workspace_id, user_id, role FROM workspace_members WHERE workspace_id = ? AND user_id = ?",
            (workspace_id, user_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------

class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    settings: Optional[dict] = None


class MemberAdd(BaseModel):
    user_id: str = Field(..., description="ID of the user to add")
    role: str = Field(default="member", description="admin | member")


class MemberRoleUpdate(BaseModel):
    role: str = Field(..., description="owner | admin | member")


# --------------------------------------------------------------------------
# Workspace CRUD
# --------------------------------------------------------------------------

@router.get("")
def list_workspaces(user: dict = Depends(get_current_user)):
    """List workspaces the current user belongs to (with role)."""
    conn = db.get_db()
    try:
        rows = conn.execute(
            "SELECT w.*, m.role FROM workspaces w "
            "JOIN workspace_members m ON w.id = m.workspace_id "
            "WHERE m.user_id = ? ORDER BY w.created_at",
            (user["id"],),
        ).fetchall()
    finally:
        conn.close()
    return {"workspaces": [_workspace_payload(r) for r in rows]}


@router.post("", status_code=201)
def create_workspace(payload: WorkspaceCreate, user: dict = Depends(get_current_user)):
    """Create a workspace; the creator becomes its owner."""
    now = _now_iso()
    workspace_id = uuid.uuid4().hex
    slug = f"{_slugify(payload.name)}-{uuid.uuid4().hex[:6]}"

    conn = db.get_db()
    try:
        conn.execute(
            "INSERT INTO workspaces (id, name, slug, owner_user_id, settings, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (workspace_id, payload.name, slug, user["id"], "{}", now),
        )
        conn.execute(
            "INSERT INTO workspace_members (workspace_id, user_id, role, created_at) VALUES (?, ?, ?, ?)",
            (workspace_id, user["id"], "owner", now),
        )
        conn.commit()
    finally:
        conn.close()

    conn = db.get_db()
    try:
        row = conn.execute("SELECT * FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
    finally:
        conn.close()
    return _workspace_payload(row)


@router.get("/{workspace_id}")
def get_workspace(workspace: dict = Depends(get_current_workspace)):
    """Get a workspace the caller belongs to."""
    return _workspace_payload(workspace)


@router.patch("/{workspace_id}")
def update_workspace(
    payload: WorkspaceUpdate,
    workspace: dict = Depends(require_workspace_role("owner", "admin")),
):
    """Update workspace name/settings (owner or admin only)."""
    updates, params = [], []
    if payload.name is not None:
        updates.append("name = ?")
        params.append(payload.name)
    if payload.settings is not None:
        updates.append("settings = ?")
        params.append(json.dumps(payload.settings))
    if not updates:
        return _workspace_payload(workspace)

    params.append(workspace["id"])
    conn = db.get_db()
    try:
        # nosec B608: SET clause built from hardcoded column names; values parameterized.
        conn.execute(f"UPDATE workspaces SET {', '.join(updates)} WHERE id = ?", params)  # nosec B608
        conn.commit()
        row = conn.execute("SELECT * FROM workspaces WHERE id = ?", (workspace["id"],)).fetchone()
    finally:
        conn.close()
    return _workspace_payload(row)


@router.delete("/{workspace_id}", status_code=204)
def delete_workspace(workspace: dict = Depends(require_workspace_role("owner"))):
    """Delete a workspace (owner only). Runs and agents cascade."""
    conn = db.get_db()
    try:
        conn.execute("DELETE FROM agent_runs WHERE workspace_id = ?", (workspace["id"],))
        conn.execute("DELETE FROM workspaces WHERE id = ?", (workspace["id"],))
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Member management
# --------------------------------------------------------------------------

@router.get("/{workspace_id}/members")
def list_members(workspace: dict = Depends(get_current_workspace)):
    """List workspace members (any member)."""
    conn = db.get_db()
    try:
        rows = conn.execute(
            "SELECT m.user_id, m.role, m.created_at, u.name, u.email, u.avatar_url "
            "FROM workspace_members m JOIN users u ON u.id = m.user_id "
            "WHERE m.workspace_id = ? ORDER BY m.created_at",
            (workspace["id"],),
        ).fetchall()
    finally:
        conn.close()
    return {"members": [dict(r) for r in rows]}


@router.post("/{workspace_id}/members", status_code=201)
def add_member(
    payload: MemberAdd,
    workspace: dict = Depends(require_workspace_role("owner", "admin")),
):
    """Add a member to the workspace (owner or admin)."""
    if payload.role not in _ADDABLE_ROLES:
        raise HTTPException(status_code=422, detail=f"Role must be one of: {sorted(_ADDABLE_ROLES)}")
    if not _user_exists(payload.user_id):
        raise HTTPException(status_code=404, detail="User not found")
    if _get_membership(workspace["id"], payload.user_id) is not None:
        raise HTTPException(status_code=409, detail="User is already a member")

    conn = db.get_db()
    try:
        conn.execute(
            "INSERT INTO workspace_members (workspace_id, user_id, role, created_at) VALUES (?, ?, ?, ?)",
            (workspace["id"], payload.user_id, payload.role, _now_iso()),
        )
        conn.commit()
    finally:
        conn.close()
    return {"workspace_id": workspace["id"], "user_id": payload.user_id, "role": payload.role}


@router.patch("/{workspace_id}/members/{user_id}")
def update_member_role(
    user_id: str,
    payload: MemberRoleUpdate,
    workspace: dict = Depends(require_workspace_role("owner")),
):
    """Change a member's role (owner only). The workspace owner cannot be demoted."""
    if payload.role not in _ROLES:
        raise HTTPException(status_code=422, detail=f"Role must be one of: {sorted(_ROLES)}")
    membership = _get_membership(workspace["id"], user_id)
    if membership is None:
        raise HTTPException(status_code=404, detail="User is not a member")
    if workspace["owner_user_id"] == user_id and payload.role != "owner":
        raise HTTPException(status_code=400, detail="The workspace owner cannot be demoted")

    conn = db.get_db()
    try:
        conn.execute(
            "UPDATE workspace_members SET role = ? WHERE workspace_id = ? AND user_id = ?",
            (payload.role, workspace["id"], user_id),
        )
        conn.commit()
    finally:
        conn.close()
    return {"workspace_id": workspace["id"], "user_id": user_id, "role": payload.role}


@router.delete("/{workspace_id}/members/{user_id}", status_code=204)
def remove_member(
    user_id: str,
    workspace: dict = Depends(require_workspace_role("owner", "admin")),
):
    """Remove a member (owner or admin). The workspace owner cannot be removed."""
    membership = _get_membership(workspace["id"], user_id)
    if membership is None:
        raise HTTPException(status_code=404, detail="User is not a member")
    if workspace["owner_user_id"] == user_id:
        raise HTTPException(status_code=400, detail="The workspace owner cannot be removed")

    conn = db.get_db()
    try:
        conn.execute(
            "DELETE FROM workspace_members WHERE workspace_id = ? AND user_id = ?",
            (workspace["id"], user_id),
        )
        conn.commit()
    finally:
        conn.close()

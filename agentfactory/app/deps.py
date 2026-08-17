"""
FastAPI dependencies for the platform API.

- ``get_current_user`` — resolves the caller from the Bearer access token.
- ``get_current_workspace`` — resolves the ``{workspace_id}`` path param and
  enforces workspace membership (403 for non-members, 404 for unknown).
- ``require_workspace_role`` — RBAC gate (owner/admin/member).
"""

from typing import Callable, Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agentfactory.app import db, security

bearer_scheme = HTTPBearer(auto_error=False)


def user_payload(user: dict) -> dict:
    """Serialize a user row for API responses (safe fields only — never the password hash)."""
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "avatar_url": user["avatar_url"],
        "created_at": user["created_at"],
    }


def _get_user(user_id: Optional[str]) -> Optional[dict]:
    if not user_id:
        return None
    conn = db.get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict:
    """Resolve the authenticated user from the Bearer access token."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = security.decode_access_token(credentials.credentials)
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid or expired token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = _get_user(payload.get("sub"))
    if user is None:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return user


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


def get_current_workspace(
    workspace_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Resolve the workspace from the path and enforce membership."""
    conn = db.get_db()
    try:
        row = conn.execute("SELECT * FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if _get_membership(workspace_id, user["id"]) is None:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")
    return dict(row)


def require_workspace_role(*roles: str) -> Callable:
    """Dependency factory: require one of the given roles in the workspace."""

    def checker(
        workspace: dict = Depends(get_current_workspace),
        user: dict = Depends(get_current_user),
    ) -> dict:
        membership = _get_membership(workspace["id"], user["id"])
        if membership is None or membership["role"] not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Requires workspace role: {', '.join(roles)}",
            )
        return workspace

    return checker

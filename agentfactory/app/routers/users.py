"""
User router — ``GET /api/v1/me`` profile endpoint (Phase 1, task 1.2).

Returns the authenticated user plus the workspaces they belong to (with
their role in each), which is what the dashboard shell needs on load.
"""

from fastapi import APIRouter, Depends

from agentfactory.app import db
from agentfactory.app.deps import get_current_user, user_payload

router = APIRouter(tags=["users"])


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    """Return the current user and their workspace memberships."""
    conn = db.get_db()
    try:
        rows = conn.execute(
            "SELECT w.*, m.role FROM workspaces w JOIN workspace_members m ON w.id = m.workspace_id "
            "WHERE m.user_id = ? ORDER BY w.created_at",
            (user["id"],),
        ).fetchall()
    finally:
        conn.close()
    workspaces = [dict(r) for r in rows]
    return {"user": user_payload(user), "workspaces": workspaces}

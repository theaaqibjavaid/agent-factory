"""
Proposals router — the human-in-the-loop approval inbox (Phase 2.3).

When an agent runs with ``hitl_mode=gate``, a proposal is created instead of
executing. Approvers (any workspace member) can approve, reject, or modify it:

- ``approve`` — the linked run is started immediately.
- ``reject`` — the proposal (and its run) is cancelled.
- ``modify`` — plan/notes are updated; the proposal stays pending so it can
  be approved with the amended instructions.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agentfactory.app import db
from agentfactory.app.deps import get_current_user, get_current_workspace
from agentfactory.crypto import decrypt_field, encrypt_field
from agentfactory.runtime import execute_run

router = APIRouter(tags=["proposals"], dependencies=[Depends(get_current_user)])

_ACTIONS = {"approve", "reject", "modify"}
_STATUSES = {"pending", "approved", "rejected", "modified", "executed", "cancelled"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _proposal_payload(row) -> dict:
    data = dict(row)
    # S-9 encryption-at-rest: plans and decision notes decrypt transparently.
    for col in ("plan", "decision_notes"):
        data[col] = decrypt_field(data.get(col))
    return data


def _get_proposal(workspace_id: str, proposal_id: str) -> Optional[dict]:
    conn = db.get_db()
    try:
        row = conn.execute(
            "SELECT * FROM proposals WHERE id = ? AND workspace_id = ?",
            (proposal_id, workspace_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _get_run_for_proposal(proposal: dict) -> Optional[dict]:
    """Find the run this proposal gates (linked at creation time)."""
    if not proposal.get("run_id"):
        return None
    conn = db.get_db()
    try:
        row = conn.execute("SELECT * FROM agent_runs WHERE id = ?", (proposal["run_id"],)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------

class ReviewRequest(BaseModel):
    action: str = Field(..., description="approve | reject | modify")
    notes: Optional[str] = Field(default=None, max_length=20000)


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@router.get("/workspaces/{workspace_id}/proposals")
def list_proposals(
    workspace: dict = Depends(get_current_workspace),
    status: Optional[str] = None,
    limit: int = 50,
):
    """List proposals in a workspace, newest first."""
    if status and status not in _STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {sorted(_STATUSES)}")

    query = "SELECT * FROM proposals WHERE workspace_id = ?"
    params: list = [workspace["id"]]
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    conn = db.get_db()
    try:
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()
    return {"proposals": [_proposal_payload(r) for r in rows]}


@router.get("/workspaces/{workspace_id}/proposals/{proposal_id}")
def get_proposal(proposal_id: str, workspace: dict = Depends(get_current_workspace)):
    """Get a proposal's detail (title, plan, status, decision notes)."""
    proposal = _get_proposal(workspace["id"], proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return _proposal_payload(proposal)


@router.post("/workspaces/{workspace_id}/proposals/{proposal_id}/review")
async def review_proposal(
    proposal_id: str,
    payload: ReviewRequest,
    workspace: dict = Depends(get_current_workspace),
    user: dict = Depends(get_current_user),
):
    """Approve, reject, or modify a gated proposal (Phase 2.3)."""
    action = payload.action.strip().lower()
    if action not in _ACTIONS:
        raise HTTPException(status_code=422, detail=f"action must be one of {sorted(_ACTIONS)}")

    proposal = _get_proposal(workspace["id"], proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal["status"] not in ("pending", "modified"):
        raise HTTPException(status_code=409, detail=f"Proposal is already {proposal['status']}")

    now = _now_iso()
    conn = db.get_db()
    try:
        if action == "approve":
            conn.execute(
                "UPDATE proposals SET status = 'approved', decision_notes = ?, updated_at = ? WHERE id = ?",
                (encrypt_field(payload.notes), now, proposal_id),
            )
            conn.commit()
            run = _get_run_for_proposal(proposal)
            run_id = run["id"] if run else None
            if run_id:
                conn.execute(
                    "UPDATE agent_runs SET status = 'pending', updated_at = ? WHERE id = ?",
                    (now, run_id),
                )
                conn.commit()
        elif action == "reject":
            conn.execute(
                "UPDATE proposals SET status = 'rejected', decision_notes = ?, updated_at = ? WHERE id = ?",
                (encrypt_field(payload.notes), now, proposal_id),
            )
            conn.commit()
            run = _get_run_for_proposal(proposal)
            if run:
                conn.execute(
                    "UPDATE agent_runs SET status = 'cancelled', updated_at = ? WHERE id = ?",
                    (now, run["id"]),
                )
                conn.commit()
        else:  # modify
            new_plan = proposal["plan"] if payload.notes is None else encrypt_field(payload.notes)
            conn.execute(
                "UPDATE proposals SET status = 'modified', decision_notes = ?, plan = ?, updated_at = ? WHERE id = ?",
                (encrypt_field(payload.notes), new_plan, now, proposal_id),
            )
            conn.commit()
    finally:
        conn.close()

    if action == "approve":
        run = _get_run_for_proposal(proposal)
        if run:
            asyncio.get_running_loop().create_task(execute_run(run["id"]))
            return {"status": "approved", "run_id": run["id"]}
        return {"status": "approved", "run_id": None}

    if action == "reject":
        return {"status": "rejected"}

    return {"status": "modified", "proposal_id": proposal_id}

"""
Runs router — create and stream agent runs (Phase 2.2/2.3/2.6).

- ``POST .../agents/{agent_id}/runs`` creates a run. With ``hitl_mode=auto``
  the run starts immediately in the background; with ``hitl_mode=gate`` a
  proposal is created instead and execution waits for approval (2.3).
- ``GET .../runs/{run_id}/events`` streams SSE events (design.md §6):
  ``run.start | token | tool_call | tool_result | verify | memory | cost | run.end | error``
- ``POST .../runs/{run_id}/retry`` recovers FAILED runs (2.6).

Every route enforces workspace membership; runs are scoped to their workspace.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agentfactory.app import db
from agentfactory.app.deps import get_current_user, get_current_workspace
from agentfactory.crypto import encrypt_field
from agentfactory.runtime import (
    execute_run,
    get_broker,
    render_agent_config,
    reset_broker,
    retry_run,
    start_run_execution,
)

router = APIRouter(tags=["runs"], dependencies=[Depends(get_current_user)])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_payload(row) -> dict:
    data = dict(row)
    # S-9 encryption-at-rest: result/error may be Fernet tokens — decrypt for API consumers.
    from agentfactory.crypto import decrypt_field
    for col in ("result", "error"):
        data[col] = decrypt_field(data.get(col))
    for col in ("stats", "config_snapshot"):
        if isinstance(data.get(col), str):
            try:
                data[col] = json.loads(data[col])
            except json.JSONDecodeError:
                data[col] = None
    return data


def _get_agent(workspace_id: str, agent_id: str) -> Optional[dict]:
    conn = db.get_db()
    try:
        row = conn.execute(
            "SELECT * FROM agents WHERE id = ? AND workspace_id = ?",
            (agent_id, workspace_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _get_run(workspace_id: str, run_id: str) -> Optional[dict]:
    conn = db.get_db()
    try:
        row = conn.execute(
            "SELECT * FROM agent_runs WHERE id = ? AND workspace_id = ?",
            (run_id, workspace_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------

class RunCreate(BaseModel):
    task: str = Field(..., min_length=1, max_length=50000)


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@router.post("/workspaces/{workspace_id}/agents/{agent_id}/runs", status_code=201)
async def create_run(
    agent_id: str,
    payload: RunCreate,
    workspace: dict = Depends(get_current_workspace),
    user: dict = Depends(get_current_user),
):
    """Create a run. Auto mode starts immediately; gate mode waits for approval."""
    agent = _get_agent(workspace["id"], agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    now = _now_iso()
    run_id = uuid4().hex
    snapshot = json.dumps(render_agent_config(agent))

    conn = db.get_db()
    try:
        status = "pending_approval" if agent["hitl_mode"] == "gate" else "pending"

        conn.execute(
            """
            INSERT INTO agent_runs (id, agent_id, workspace_id, task, status,
                                    config_snapshot, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, agent_id, workspace["id"], payload.task, status, snapshot, now, now),
        )
        conn.commit()
    finally:
        conn.close()

    response = {"run_id": run_id, "status": status, "agent_id": agent_id, "task": payload.task}

    if status == "pending":
        start_run_execution(run_id)
        response["status"] = "running"
    else:
        # HITL gate (Phase 2.3): create the proposal the Approvals inbox will show.
        proposal_id = uuid4().hex
        conn = db.get_db()
        try:
            conn.execute(
                """
                INSERT INTO proposals (id, workspace_id, agent_id, run_id, title, plan, status,
                                       created_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (proposal_id, workspace["id"], agent_id, run_id, payload.task[:200],
                 encrypt_field(payload.task), "pending", user["id"], now, now),
            )
            conn.commit()
        finally:
            conn.close()
        # Notifications (Phase 5.4): a gated proposal awaits human review.
        try:
            from agentfactory.app.notify import notify_proposal_created

            notify_proposal_created(_settings_for(workspace["id"]), {
                "id": proposal_id,
                "title": payload.task[:200],
                "plan": payload.task,
            }, agent["name"])
        except Exception:  # noqa: BLE001 — notifications must never break run creation
            pass
        response["proposal_id"] = proposal_id

    return response


def _settings_for(workspace_id: str) -> dict:
    """Decode a workspace's settings JSON (Phase 5.4 notification config lives there)."""
    conn = db.get_db()
    try:
        row = conn.execute("SELECT settings FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return {}
    try:
        parsed = json.loads(row["settings"])
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


@router.get("/workspaces/{workspace_id}/runs")
def list_runs(
    workspace: dict = Depends(get_current_workspace),
    agent_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    """List runs in a workspace, newest first."""
    query = "SELECT * FROM agent_runs WHERE workspace_id = ?"
    params: list = [workspace["id"]]
    if agent_id:
        query += " AND agent_id = ?"
        params.append(agent_id)
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
    return {"runs": [_run_payload(r) for r in rows]}


@router.get("/workspaces/{workspace_id}/runs/{run_id}")
def get_run(run_id: str, workspace: dict = Depends(get_current_workspace)):
    """Get a run's detail (result, stats, error)."""
    run = _get_run(workspace["id"], run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return _run_payload(run)


@router.get("/workspaces/{workspace_id}/runs/{run_id}/events")
async def run_events(
    run_id: str,
    workspace: dict = Depends(get_current_workspace),
    after_seq: int = Query(default=0, ge=0),
):
    """SSE stream of run events (design.md §6). Replays from after_seq, then live."""
    run = _get_run(workspace["id"], run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    broker = get_broker(run_id, workspace_id=workspace["id"])

    async def event_generator():
        async for event in broker.stream(after_seq=after_seq):
            data = json.dumps(event)
            yield f"event: {event['event']}\ndata: {data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/workspaces/{workspace_id}/runs/{run_id}/retry")
async def retry_run_endpoint(run_id: str, workspace: dict = Depends(get_current_workspace)):
    """Recover a FAILED run: resets it to pending and restarts execution (2.6)."""
    run = _get_run(workspace["id"], run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run["status"] != "failed":
        raise HTTPException(status_code=409, detail="Only failed runs can be retried")
    if not retry_run(run_id):
        raise HTTPException(status_code=409, detail="Run could not be retried")

    # Fresh event stream for the retry execution, then restart on the loop.
    reset_broker(run_id, workspace_id=workspace["id"])
    asyncio.get_running_loop().create_task(execute_run(run_id))
    return {"run_id": run_id, "status": "running", "retries": run.get("retries", 0) + 1}

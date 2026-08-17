"""
Terminal router (Phase 5.1) — workspace-scoped PTY shells over REST + WebSocket.

- ``POST .../terminal/sessions`` — create a shell pinned to the workspace
  sandbox root (optional ``cwd`` must stay inside it).
- ``GET/DELETE .../terminal/sessions`` — list / kill sessions (kill-on-close).
- ``POST .../sessions/{id}/write`` — send input through the destructive-command
  guard; a matching command returns ``{blocked: true, command, reason}`` and is
  only dispatched after the caller resubmits it with ``confirm: true``.
- ``GET .../sessions/{id}/output`` — drain buffered output (polling clients).
- WebSocket ``.../terminal/ws?token=...&session=...`` — full-duplex transport:
  ``{type: input|confirm|resize|close}`` messages in, ``{type: output|confirm
  |closed}`` messages out.

The WebSocket authenticates via the access token in the query string (browsers
cannot set headers on WebSocket connections), then enforces workspace
membership like every other route.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from agentfactory.app import db, security
from agentfactory.app.deps import get_current_user, get_current_workspace
from agentfactory.runtime import workspace_root_for
from agentfactory.terminal import get_terminal_manager

# NOTE: no router-level auth dependency — it would also apply to the
# WebSocket route, where HTTPBearer cannot run. Each REST route declares
# Depends(get_current_user) explicitly; the WebSocket authenticates via the
# access token in its query string.
router = APIRouter(tags=["terminal"])


def _session_payload(session) -> dict:
    return {
        "id": session.id,
        "workspace_id": getattr(session, "workspace_id", None),
        "cwd": session.workspace_root,
        "alive": session.alive,
        "pending_confirmation": session.pending_confirmation,
        "pending_reason": session.pending_reason,
        "created_at": session.created_at,
    }


def _auth_ws(token: str, workspace_id: str) -> dict:
    """Authenticate a WebSocket (token via query string) + enforce membership."""
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        payload = security.decode_access_token(token)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {e}") from e

    conn = db.get_db()
    try:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (payload.get("sub"),)).fetchone()
        if user is None:
            raise HTTPException(status_code=401, detail="User no longer exists")
        membership = conn.execute(
            "SELECT role FROM workspace_members WHERE workspace_id = ? AND user_id = ?",
            (workspace_id, user["id"]),
        ).fetchone()
    finally:
        conn.close()
    if membership is None:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")
    return dict(user)


# --------------------------------------------------------------------------
# REST
# --------------------------------------------------------------------------

class SessionCreate(BaseModel):
    cwd: Optional[str] = Field(default=None, max_length=500)


class SessionWrite(BaseModel):
    data: str = Field(..., min_length=1, max_length=10000)
    confirm: bool = False


class SessionResize(BaseModel):
    cols: int = Field(..., ge=1, le=500)
    rows: int = Field(..., ge=1, le=500)


@router.post("/workspaces/{workspace_id}/terminal/sessions", status_code=201)
def create_session(
    payload: SessionCreate,
    _user: dict = Depends(get_current_user),
    workspace: dict = Depends(get_current_workspace),
):
    """Create a workspace-scoped shell session."""
    manager = get_terminal_manager()
    try:
        session = manager.create(workspace["id"], workspace_root_for(workspace["id"]), cwd=payload.cwd)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return _session_payload(session)


@router.get("/workspaces/{workspace_id}/terminal/sessions")
def list_sessions(
    _user: dict = Depends(get_current_user),
    workspace: dict = Depends(get_current_workspace),
):
    """List live sessions for the workspace."""
    sessions = get_terminal_manager().list_for_workspace(workspace["id"])
    return {"sessions": [_session_payload(s) for s in sessions]}


@router.get("/workspaces/{workspace_id}/terminal/sessions/{session_id}")
def get_session(
    session_id: str,
    _user: dict = Depends(get_current_user),
    workspace: dict = Depends(get_current_workspace),
):
    """Session detail + any buffered output."""
    session = get_terminal_manager().get(session_id)
    if session is None or session.workspace_id != workspace["id"]:
        raise HTTPException(status_code=404, detail="Session not found")
    return _session_payload(session)


@router.get("/workspaces/{workspace_id}/terminal/sessions/{session_id}/output")
def read_output(
    session_id: str,
    _user: dict = Depends(get_current_user),
    workspace: dict = Depends(get_current_workspace),
):
    """Drain buffered PTY output (polling transport for non-WS clients)."""
    session = get_terminal_manager().get(session_id)
    if session is None or session.workspace_id != workspace["id"]:
        raise HTTPException(status_code=404, detail="Session not found")
    data = session.read_output(timeout=0.05)
    return {"output": data.decode("utf-8", errors="replace"), "alive": session.alive}


@router.post("/workspaces/{workspace_id}/terminal/sessions/{session_id}/write")
def write_input(
    session_id: str,
    payload: SessionWrite,
    _user: dict = Depends(get_current_user),
    workspace: dict = Depends(get_current_workspace),
):
    """Write input, gated by the destructive-command confirmation flow."""
    session = get_terminal_manager().get(session_id)
    if session is None or session.workspace_id != workspace["id"]:
        raise HTTPException(status_code=404, detail="Session not found")

    if payload.confirm:
        result = session.submit_input(payload.data)
    elif session.pending_confirmation is not None:
        # New input while a confirmation is pending: treat as not confirmed.
        result = {
            "blocked": True,
            "command": session.pending_confirmation,
            "reason": session.pending_reason or "destructive command",
        }
    else:
        result = session.submit_input(payload.data)
    return result


@router.post("/workspaces/{workspace_id}/terminal/sessions/{session_id}/resize")
def resize_session(
    session_id: str,
    payload: SessionResize,
    _user: dict = Depends(get_current_user),
    workspace: dict = Depends(get_current_workspace),
):
    """Resize the PTY window (cols x rows)."""
    session = get_terminal_manager().get(session_id)
    if session is None or session.workspace_id != workspace["id"]:
        raise HTTPException(status_code=404, detail="Session not found")
    session.resize(payload.cols, payload.rows)
    return {"ok": True}


@router.delete("/workspaces/{workspace_id}/terminal/sessions/{session_id}", status_code=204)
def delete_session(
    session_id: str,
    _user: dict = Depends(get_current_user),
    workspace: dict = Depends(get_current_workspace),
):
    """Kill the session's process group and close it (kill-on-disconnect)."""
    session = get_terminal_manager().get(session_id)
    if session is None or session.workspace_id != workspace["id"]:
        raise HTTPException(status_code=404, detail="Session not found")
    get_terminal_manager().close(session_id)


# --------------------------------------------------------------------------
# WebSocket
# --------------------------------------------------------------------------

@router.websocket("/workspaces/{workspace_id}/terminal/ws")
async def terminal_ws(websocket: WebSocket, workspace_id: str):
    """Full-duplex terminal transport (token via ``?token=`` query param)."""
    try:
        token = websocket.query_params.get("token", "")
        _auth_ws(token, workspace_id)
        await websocket.accept()
    except HTTPException as e:
        await websocket.close(code=4401, reason=str(e.detail))
        return
    except Exception:  # noqa: BLE001
        await websocket.close(code=4401, reason="Authentication required")
        return

    session_id = websocket.query_params.get("session")
    manager = get_terminal_manager()
    session = manager.get(session_id) if session_id else None
    if session is None or session.workspace_id != workspace_id:
        await websocket.send_json({"type": "error", "message": "Unknown terminal session"})
        await websocket.close()
        return

    try:
        # Kick off output pumping on the same loop.
        import asyncio

        async def pump():
            while True:
                data = session.read_output(timeout=0.1)
                if data:
                    await websocket.send_json({"type": "output", "data": data.decode("utf-8", errors="replace")})
                if not session.alive:
                    await websocket.send_json({"type": "closed"})
                    break
                await asyncio.sleep(0.05)

        pump_task = asyncio.create_task(pump())
        try:
            while True:
                message = await websocket.receive_json()
                mtype = message.get("type")
                if mtype == "input":
                    result = session.submit_input(message.get("data", ""))
                    if result.get("blocked"):
                        await websocket.send_json({
                            "type": "confirm",
                            "command": result.get("command", ""),
                            "reason": result.get("reason", "destructive command"),
                        })
                elif mtype == "confirm":
                    result = session.submit_input(message.get("data", ""))
                    if result.get("blocked") and not result.get("confirmed"):
                        await websocket.send_json({
                            "type": "confirm",
                            "command": result.get("command", ""),
                            "reason": result.get("reason", "destructive command"),
                        })
                elif mtype == "resize":
                    session.resize(int(message.get("cols", 80)), int(message.get("rows", 24)))
                elif mtype == "close":
                    break
        except WebSocketDisconnect:
            pass
        finally:
            pump_task.cancel()
    finally:
        # Kill-on-disconnect: closing the websocket terminates the shell.
        manager.close(session.id)
        try:
            await websocket.close()
        except RuntimeError:  # pragma: no cover - already closed
            pass

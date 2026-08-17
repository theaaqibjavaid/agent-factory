"""
MCP router — manage stdio/SSE MCP servers from the UI (Phase 4.3).

- ``POST .../mcp/test`` — spawn the server, run the hardened MCP handshake
  (Phase 0.7 client) and list its tools; no registration happens.
- CRUD on ``mcp_servers`` with command allowlisting (env
  ``AGENTFACTORY_MCP_ALLOWED_COMMANDS``) and env allowlisting per server.
- ``POST .../mcp/{id}/refresh-tools`` — probe a saved server and persist the
  discovered tool list into its metadata for the agent editor.

The runtime attaches an agent's configured servers at run start
(``runtime.PlatformAgentRuntime._attach_mcp_tools``); per-tool enablement is
stored in metadata and honored there.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from agentfactory.app import db
from agentfactory.app.deps import get_current_user, get_current_workspace, require_workspace_role
from agentfactory.mcp_integration import MCPClient, MCPServerConfig

router = APIRouter(tags=["mcp"], dependencies=[Depends(get_current_user)])

_DEFAULT_ALLOWED_COMMANDS = "npx,uvx,python,python3,node,deno,bun"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _allowed_commands() -> set:
    raw = os.getenv("AGENTFACTORY_MCP_ALLOWED_COMMANDS", _DEFAULT_ALLOWED_COMMANDS)
    return {c.strip() for c in raw.split(",") if c.strip()}


def _server_payload(row) -> dict:
    data = dict(row)
    for col in ("args", "env_allow"):
        if isinstance(data.get(col), str):
            try:
                data[col] = json.loads(data[col])
            except json.JSONDecodeError:
                data[col] = []
    try:
        data["metadata"] = json.loads(data.get("metadata") or "{}")
    except (json.JSONDecodeError, TypeError):
        data["metadata"] = {}
    return data


def _get_server(workspace_id: str, server_id: str) -> Optional[dict]:
    conn = db.get_db()
    try:
        row = conn.execute(
            "SELECT * FROM mcp_servers WHERE id = ? AND workspace_id = ?",
            (server_id, workspace_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _validate_command(command: str) -> None:
    base = command.strip().split()[0]
    # Match on the basename so absolute paths (e.g. /usr/bin/python3) still
    # resolve against the allowlist.
    name = os.path.basename(base)
    if name not in _allowed_commands():
        raise HTTPException(
            status_code=422,
            detail=f"Command '{base}' is not in the MCP command allowlist ({sorted(_allowed_commands())})",
        )


async def _probe(config: MCPServerConfig) -> List[Dict[str, Any]]:
    """Connect, list tools, and close — returns the tool manifest."""
    client = MCPClient(config)
    try:
        await client.connect()
        tools = await client.list_tools()
        return [{
            "name": t.name,
            "description": t.description,
            "input_schema": t.input_schema,
            "server": t.server_name,
        } for t in tools]
    finally:
        await client.close()


class MCPServerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    transport: str = Field(default="stdio")
    command: Optional[str] = None
    args: List[str] = Field(default_factory=list)
    url: Optional[str] = None
    env_allow: List[str] = Field(default_factory=list)
    timeout: float = Field(default=10.0, ge=1.0, le=120.0)
    enabled: bool = True

    @field_validator("name", "transport")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("transport")
    @classmethod
    def _transport(cls, value: str) -> str:
        if value not in ("stdio", "sse"):
            raise ValueError("transport must be stdio or sse")
        return value


class MCPServerUpdate(BaseModel):
    transport: Optional[str] = None
    command: Optional[str] = None
    args: Optional[List[str]] = None
    url: Optional[str] = None
    env_allow: Optional[List[str]] = None
    timeout: Optional[float] = Field(default=None, ge=1.0, le=120.0)
    enabled: Optional[bool] = None


class MCPTestRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    transport: str = "stdio"
    command: Optional[str] = None
    args: List[str] = Field(default_factory=list)
    url: Optional[str] = None
    env_allow: List[str] = Field(default_factory=list)
    timeout: float = Field(default=10.0, ge=1.0, le=120.0)


@router.get("/workspaces/{workspace_id}/mcp")
def list_servers(workspace: dict = Depends(get_current_workspace)):
    """List MCP servers in the workspace."""
    conn = db.get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM mcp_servers WHERE workspace_id = ? ORDER BY created_at",
            (workspace["id"],),
        ).fetchall()
    finally:
        conn.close()
    return {"servers": [_server_payload(r) for r in rows]}


@router.post("/workspaces/{workspace_id}/mcp/test")
async def test_connection(payload: MCPTestRequest, workspace: dict = Depends(get_current_workspace)):
    """Probe an MCP server config without saving it (Phase 4.3 exit criterion)."""
    if payload.transport == "sse":
        raise HTTPException(status_code=422, detail="SSE transport probing is not supported yet")
    if not payload.command:
        raise HTTPException(status_code=422, detail="command is required for stdio transport")
    _validate_command(payload.command)

    config = MCPServerConfig(
        name=payload.name,
        command=payload.command,
        args=payload.args,
        env={k: os.environ[k] for k in payload.env_allow if k in os.environ},
        timeout=payload.timeout,
    )
    try:
        tools = await _probe(config)
    except Exception as e:  # noqa: BLE001 — surface connection errors to the UI
        return {"ok": False, "error": str(e), "tools": []}
    return {"ok": True, "tools": tools, "count": len(tools)}


@router.post("/workspaces/{workspace_id}/mcp", status_code=201)
def create_server(
    payload: MCPServerCreate,
    workspace: dict = Depends(require_workspace_role("owner", "admin")),
):
    """Register an MCP server."""
    if payload.transport == "stdio":
        if not payload.command:
            raise HTTPException(status_code=422, detail="command is required for stdio transport")
        _validate_command(payload.command)
    elif not payload.url:
        raise HTTPException(status_code=422, detail="url is required for SSE transport")

    now = _now_iso()
    server_id = uuid.uuid4().hex
    conn = db.get_db()
    try:
        conn.execute(
            """
            INSERT INTO mcp_servers (id, workspace_id, name, transport, command, args, url,
                                     env_allow, timeout, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (server_id, workspace["id"], payload.name, payload.transport, payload.command,
             json.dumps(payload.args), payload.url, json.dumps(payload.env_allow),
             payload.timeout, 1 if payload.enabled else 0, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM mcp_servers WHERE id = ?", (server_id,)).fetchone()
    finally:
        conn.close()
    return _server_payload(row)


@router.patch("/workspaces/{workspace_id}/mcp/{server_id}")
def update_server(
    server_id: str,
    payload: MCPServerUpdate,
    workspace: dict = Depends(require_workspace_role("owner", "admin")),
):
    """Update an MCP server registration."""
    existing = _get_server(workspace["id"], server_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="MCP server not found")

    updates: List[str] = []
    params: List[Any] = []

    def set_field(column: str, value: Any) -> None:
        updates.append(f"{column} = ?")
        params.append(value)

    if payload.transport is not None:
        if payload.transport not in ("stdio", "sse"):
            raise HTTPException(status_code=422, detail="transport must be stdio or sse")
        set_field("transport", payload.transport)
    if payload.command is not None:
        _validate_command(payload.command)
        set_field("command", payload.command)
    if payload.args is not None:
        set_field("args", json.dumps(payload.args))
    if payload.url is not None:
        set_field("url", payload.url)
    if payload.env_allow is not None:
        set_field("env_allow", json.dumps(payload.env_allow))
    if payload.timeout is not None:
        set_field("timeout", payload.timeout)
    if payload.enabled is not None:
        set_field("enabled", 1 if payload.enabled else 0)

    if not updates:
        return _server_payload(existing)
    params.extend([server_id, workspace["id"]])
    conn = db.get_db()
    try:
        conn.execute(
            f"UPDATE mcp_servers SET {', '.join(updates)} WHERE id = ? AND workspace_id = ?",
            params,
        )
        conn.commit()
        row = conn.execute("SELECT * FROM mcp_servers WHERE id = ?", (server_id,)).fetchone()
    finally:
        conn.close()
    return _server_payload(row)


@router.delete("/workspaces/{workspace_id}/mcp/{server_id}", status_code=204)
def delete_server(server_id: str, workspace: dict = Depends(require_workspace_role("owner", "admin"))):
    """Delete an MCP server registration."""
    conn = db.get_db()
    try:
        cur = conn.execute(
            "DELETE FROM mcp_servers WHERE id = ? AND workspace_id = ?",
            (server_id, workspace["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="MCP server not found")

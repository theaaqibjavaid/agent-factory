"""
Marketplace router — curated catalog + install flows (Phase 4.5).

v1 serves a curated JSON registry (tools, skills, MCP templates) with trust
indicators (publisher, verified, safety scan). Installing writes an audit
event to ``marketplace_installs`` and, for skills/tools with install payloads,
creates a registration row in the workspace.

``GET /marketplace`` is intentionally NOT workspace-scoped (public catalog);
installs are workspace-scoped and audit-logged.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agentfactory import validation
from agentfactory.app import db
from agentfactory.app.deps import get_current_user, get_current_workspace, require_workspace_role

router = APIRouter(tags=["marketplace"], dependencies=[Depends(get_current_user)])

# Curated registry v1 — trust indicators are explicit so the UI can render
# them before install. v1.1 (per Phases.md) moves to signed manifests.
_CATALOG: Dict[str, Any] = {
    "tools": [
        {
            "id": "tool-fetch-json",
            "name": "fetch_json",
            "publisher": "agentfactory",
            "verified": True,
            "version": "1.0.0",
            "safety_level": "safe",
            "category": "web",
            "description": "Fetch a URL and parse its JSON body.",
            "code": (
                "import json\n"
                "import urllib.request\n"
                "\n"
                "def fetch_json(url: str) -> str:\n"
                "    \"\"\"Fetch url and return its JSON body as pretty text.\"\"\"\n"
                "    with urllib.request.urlopen(url, timeout=15) as resp:\n"
                "        data = json.loads(resp.read().decode('utf-8'))\n"
                "    return json.dumps(data, indent=2)[:4000]\n"
            ),
        },
        {
            "id": "tool-slugify",
            "name": "slugify",
            "publisher": "agentfactory",
            "verified": True,
            "version": "1.0.0",
            "safety_level": "safe",
            "category": "text",
            "description": "Convert a string to a URL-safe slug.",
            "code": (
                "import re\n"
                "\n"
                "def slugify(text: str) -> str:\n"
                "    \"\"\"Convert text to a lowercase, hyphenated slug.\"\"\"\n"
                "    slug = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')\n"
                "    return slug or 'untitled'\n"
            ),
        },
    ],
    "skills": [
        {
            "id": "skill-briefing",
            "name": "briefing-writer",
            "publisher": "agentfactory",
            "verified": True,
            "version": "1.0.0",
            "category": "research",
            "description": "Turns research notes into a structured executive briefing.",
            "instructions": (
                "You write concise executive briefings. Structure: 1) TL;DR (3 bullets), "
                "2) Key findings with sources, 3) Risks, 4) Recommended next step. "
                "Never invent facts — only synthesize what tools returned."
            ),
        },
        {
            "id": "skill-code-reviewer",
            "name": "code-reviewer",
            "publisher": "agentfactory",
            "verified": True,
            "version": "1.0.0",
            "category": "engineering",
            "description": "Applies senior code-review discipline: security, correctness, style.",
            "instructions": (
                "You are a senior code reviewer. Check for: security issues (injection, "
                "unsafe eval, secrets), correctness (off-by-one, race conditions), and "
                "style. Report findings as a numbered list with severity and a fix suggestion."
            ),
        },
    ],
    "mcp": [
        {
            "id": "mcp-filesystem",
            "name": "filesystem",
            "publisher": "modelcontextprotocol",
            "verified": False,
            "version": "1.0.0",
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            "description": "Official MCP filesystem server (scoped to a directory).",
        },
        {
            "id": "mcp-github",
            "name": "github",
            "publisher": "github",
            "verified": False,
            "version": "1.0.0",
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "description": "Official GitHub MCP server (needs GITHUB_TOKEN env).",
        },
    ],
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit_payload(row) -> dict:
    data = dict(row)
    try:
        data["findings"] = json.loads(data.get("findings") or "[]")
    except (json.JSONDecodeError, TypeError):
        data["findings"] = []
    return data


def _record_install(
    workspace_id: str,
    item_type: str,
    item: Dict[str, Any],
    status: str,
    findings: List[Dict[str, Any]],
    user: dict,
) -> None:
    conn = db.get_db()
    try:
        conn.execute(
            """
            INSERT INTO marketplace_installs (id, workspace_id, item_type, item_id, item_name,
                                              publisher, status, findings, installed_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (uuid.uuid4().hex, workspace_id, item_type, item["id"], item["name"],
             item.get("publisher"), status, json.dumps(findings), user["id"], _now_iso()),
        )
        conn.commit()
    finally:
        conn.close()


class MarketplaceInstall(BaseModel):
    item_type: str = Field(..., description="tool | skill | mcp")
    item_id: str = Field(..., min_length=1)


_CATALOG_KEY = {"tool": "tools", "skill": "skills", "mcp": "mcp"}


def _find_item(item_type: str, item_id: str) -> Dict[str, Any]:
    items = _CATALOG.get(_CATALOG_KEY.get(item_type, item_type), [])
    for item in items:
        if item["id"] == item_id:
            return item
    raise HTTPException(status_code=404, detail=f"Unknown {item_type} item: {item_id}")


@router.get("/marketplace")
def catalog():
    """Public curated catalog with trust indicators."""
    return {"catalog": _CATALOG, "schema_version": 1}


@router.get("/workspaces/{workspace_id}/marketplace/installs")
def installs(workspace: dict = Depends(get_current_workspace)):
    """Install audit log for the workspace (Phase 4.5)."""
    conn = db.get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM marketplace_installs WHERE workspace_id = ? ORDER BY created_at DESC LIMIT 100",
            (workspace["id"],),
        ).fetchall()
    finally:
        conn.close()
    return {"installs": [_audit_payload(r) for r in rows]}


@router.post("/workspaces/{workspace_id}/marketplace/install", status_code=201)
def install_item(
    payload: MarketplaceInstall,
    workspace: dict = Depends(require_workspace_role("owner", "admin")),
    user: dict = Depends(get_current_user),
):
    """Install a marketplace item into the workspace + record the audit event."""
    if payload.item_type not in ("tool", "skill", "mcp"):
        raise HTTPException(status_code=422, detail="item_type must be tool, skill, or mcp")
    item = _find_item(payload.item_type, payload.item_id)
    findings: List[Dict[str, Any]] = []

    if payload.item_type == "tool":
        # Re-run the same validation gate as the custom-tool editor.
        result = validation.validate_custom_code(item["code"])
        findings = [f.to_dict() for f in result.findings]
        if not result.passes:
            _record_install(workspace["id"], "tool", item, "failed", findings, user)
            raise HTTPException(status_code=422, detail={
                "message": "Marketplace tool failed static validation",
                "findings": findings,
            })
        conn = db.get_db()
        try:
            meta = {
                "description": item["description"],
                "category": item["category"],
                "safety_level": item["safety_level"],
                "cost_per_call_usd": 0.0,
                "tags": ["marketplace", item.get("publisher", "")],
                "function_name": result.function_name,
                "schema": result.schema,
                "publisher": item.get("publisher"),
                "version": item.get("version"),
            }
            conn.execute(
                """
                INSERT INTO tool_registrations (id, workspace_id, name, source, code, metadata, enabled, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (uuid.uuid4().hex, workspace["id"], item["name"], "marketplace", item["code"],
                 json.dumps(meta), 1, _now_iso()),
            )
            conn.commit()
        finally:
            conn.close()
        _record_install(workspace["id"], "tool", item, "installed", findings, user)
        return {"installed": item["name"], "type": "tool", "findings": findings}

    if payload.item_type == "skill":
        conn = db.get_db()
        try:
            meta = {
                "description": item["description"],
                "instructions": item["instructions"],
                "tools": [],
                "category": item["category"],
                "tags": ["marketplace", item.get("publisher", "")],
                "publisher": item.get("publisher"),
                "version": item.get("version"),
            }
            conn.execute(
                """
                INSERT INTO skill_registrations (id, workspace_id, name, source, metadata, enabled, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (uuid.uuid4().hex, workspace["id"], item["name"], "marketplace",
                 json.dumps(meta), 1, _now_iso()),
            )
            conn.commit()
        finally:
            conn.close()
        _record_install(workspace["id"], "skill", item, "installed", findings, user)
        return {"installed": item["name"], "type": "skill", "findings": findings}

    # MCP server template
    conn = db.get_db()
    try:
        conn.execute(
            """
            INSERT INTO mcp_servers (id, workspace_id, name, transport, command, args, url,
                                     env_allow, timeout, enabled, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (uuid.uuid4().hex, workspace["id"], item["name"], item.get("transport", "stdio"),
             item.get("command"), json.dumps(item.get("args", [])), None,
             json.dumps(["GITHUB_TOKEN"] if item.get("name") == "github" else []),
             15.0, 1, json.dumps({"publisher": item.get("publisher"), "version": item.get("version")}),
             _now_iso()),
        )
        conn.commit()
    finally:
        conn.close()
    _record_install(workspace["id"], "mcp", item, "installed", findings, user)
    return {"installed": item["name"], "type": "mcp", "findings": findings}

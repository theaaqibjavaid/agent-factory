"""
Platform API — Phase 1 multi-user backend (auth, workspaces, agents).

Mounts the ``/api/v1`` routers (auth, users, workspaces, agents) on the
platform SQLite database. The legacy approval server
(``agentfactory.app.approval_server``) is a separate app and keeps serving
``/api/agent/*`` untouched in ``LOCAL_MODE`` (Phase 1, task 1.5 — legacy
bridge). Run with: ``uvicorn agentfactory.app.main:app``.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from agentfactory.app import db
from agentfactory.app.routers import (
    agents,
    auth,
    marketplace,
    mcp,
    memories,
    models,
    observability,
    proposals,
    runs,
    skills,
    terminal,
    tools,
    users,
    workspaces,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure the platform schema exists on startup."""
    db.init_db()
    yield


app = FastAPI(
    title="AgentFactory Platform API",
    description="Multi-user control plane: auth, workspaces, agents (Phase 1)",
    version="1.1.0",
    lifespan=lifespan,
)

# CORS — explicit origins via env (comma-separated). Default: allow all (local mode).
_ALLOWED_ORIGINS = [o.strip() for o in os.getenv("AGENTFACTORY_ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=_ALLOWED_ORIGINS != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(workspaces.router, prefix="/api/v1")
app.include_router(agents.router, prefix="/api/v1")
app.include_router(runs.router, prefix="/api/v1")
app.include_router(proposals.router, prefix="/api/v1")
app.include_router(memories.router, prefix="/api/v1")
app.include_router(tools.router, prefix="/api/v1")
app.include_router(skills.router, prefix="/api/v1")
app.include_router(mcp.router, prefix="/api/v1")
app.include_router(models.router, prefix="/api/v1")
app.include_router(marketplace.router, prefix="/api/v1")
app.include_router(terminal.router, prefix="/api/v1")
app.include_router(observability.router, prefix="/api/v1")


@app.get("/health", tags=["system"])
def health():
    """Health check — returns no tokens, no sensitive data."""
    return {"status": "ok", "service": "AgentFactory Platform API", "version": "1.1.0"}


# ---------------------------------------------------------------------------
# Studio SPA static serving (Phase 6.2 — self-host one process for API + UI)
# ---------------------------------------------------------------------------
# When AGENTFACTORY_SPA_DIR points at a built Studio (web/dist), the API also
# serves the SPA: real files are returned as-is, and any other GET falls back
# to index.html so react-router deep links work. API routes registered above
# always win because they are matched before this catch-all.

_SPA_DIR = os.getenv("AGENTFACTORY_SPA_DIR", "")


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    """Serve the Studio SPA when built assets are present (self-host mode)."""
    if not _SPA_DIR:
        raise HTTPException(status_code=404, detail="Not found")

    index_path = os.path.join(_SPA_DIR, "index.html")
    requested = os.path.join(_SPA_DIR, full_path)
    # Serve real static assets; never resolve paths outside the SPA directory.
    if full_path and os.path.isfile(requested) and os.path.commonpath([_SPA_DIR, os.path.abspath(requested)]) == os.path.abspath(_SPA_DIR):
        return FileResponse(requested)
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="Not found")

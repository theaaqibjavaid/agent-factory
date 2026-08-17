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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agentfactory.app import db
from agentfactory.app.routers import agents, auth, memories, proposals, runs, users, workspaces


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure the platform schema exists on startup."""
    db.init_db()
    yield


app = FastAPI(
    title="AgentFactory Platform API",
    description="Multi-user control plane: auth, workspaces, agents (Phase 1)",
    version="0.2.0",
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


@app.get("/health", tags=["system"])
def health():
    """Health check — returns no tokens, no sensitive data."""
    return {"status": "ok", "service": "AgentFactory Platform API", "version": "0.2.0"}

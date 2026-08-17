"""
Platform database — schema v2 (users, workspaces, agents, runs, ...).

This is the multi-tenant data layer for the AgentFactory Platform (Phase 1).
It is a SEPARATE database from the v1 approval-server database
(``~/.agentfactory/approval.db``) so legacy local-mode installs keep working
untouched. Schema creation is idempotent and versioned via ``PRAGMA user_version``.
"""

import os
import sqlite3
import threading
from typing import Dict, Optional

DEFAULT_DB_PATH = os.path.join(os.path.expanduser("~"), ".agentfactory", "platform.db")

_SCHEMA_VERSION = 1

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    email         TEXT UNIQUE,
    password_hash TEXT,
    name          TEXT,
    avatar_url    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS oauth_accounts (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider     TEXT NOT NULL,
    provider_sub TEXT NOT NULL,
    UNIQUE(provider, provider_sub)
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    jti         TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    revoked_at  TEXT,
    replaced_by TEXT
);

CREATE TABLE IF NOT EXISTS workspaces (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    slug          TEXT UNIQUE NOT NULL,
    owner_user_id TEXT NOT NULL REFERENCES users(id),
    settings      TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workspace_members (
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role         TEXT NOT NULL DEFAULT 'member',   -- owner | admin | member
    created_at   TEXT NOT NULL,
    PRIMARY KEY (workspace_id, user_id)
);

CREATE TABLE IF NOT EXISTS agents (
    id                     TEXT PRIMARY KEY,
    workspace_id           TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name                   TEXT NOT NULL,
    rank                   TEXT NOT NULL DEFAULT 'Junior',
    role_description       TEXT,
    system_instructions    TEXT,
    model_preferences      TEXT NOT NULL DEFAULT '[]',
    tools                  TEXT NOT NULL DEFAULT '[]',
    skills                 TEXT NOT NULL DEFAULT '[]',
    mcp_servers            TEXT NOT NULL DEFAULT '[]',
    temperature            REAL NOT NULL DEFAULT 0.2,
    max_budget_usd_per_day REAL NOT NULL DEFAULT 5.0,
    hitl_mode              TEXT NOT NULL DEFAULT 'auto',  -- auto | gate
    max_iterations         INTEGER NOT NULL DEFAULT 20,
    status                 TEXT NOT NULL DEFAULT 'idle',
    config_snapshot        TEXT,
    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agents_workspace ON agents(workspace_id);

CREATE TABLE IF NOT EXISTS agent_runs (
    id           TEXT PRIMARY KEY,
    agent_id     TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    workspace_id TEXT NOT NULL,
    task         TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',  -- pending|running|completed|failed|cancelled
    result       TEXT,
    stats        TEXT,
    error        TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_agent ON agent_runs(agent_id);

CREATE TABLE IF NOT EXISTS proposals (
    id             TEXT PRIMARY KEY,
    workspace_id   TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    agent_id       TEXT REFERENCES agents(id) ON DELETE SET NULL,
    title          TEXT NOT NULL,
    plan           TEXT,
    status         TEXT NOT NULL DEFAULT 'pending',  -- pending|approved|rejected|modified|executed
    decision_notes TEXT,
    created_by     TEXT REFERENCES users(id),
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_proposals_workspace ON proposals(workspace_id);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id    TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    theme      TEXT NOT NULL DEFAULT 'light',
    fonts      TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

-- Extensibility registries (populated by Phase 4 tooling; schema reserved now)
CREATE TABLE IF NOT EXISTS tool_registrations (
    id           TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    source       TEXT NOT NULL DEFAULT 'builtin',  -- builtin | custom | marketplace
    code         TEXT,
    metadata     TEXT NOT NULL DEFAULT '{}',
    enabled      INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS skill_registrations (
    id           TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    source       TEXT NOT NULL DEFAULT 'builtin',
    metadata     TEXT NOT NULL DEFAULT '{}',
    enabled      INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mcp_servers (
    id           TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    transport    TEXT NOT NULL DEFAULT 'stdio',  -- stdio | sse
    command      TEXT,
    args         TEXT NOT NULL DEFAULT '[]',
    url          TEXT,
    env_allow    TEXT NOT NULL DEFAULT '[]',
    timeout      REAL NOT NULL DEFAULT 10.0,
    enabled      INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_connections (
    id           TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    provider     TEXT NOT NULL,                    -- gemini | openai | anthropic | openai_compatible
    model        TEXT NOT NULL,
    base_url     TEXT,
    key_ref      TEXT,                             -- reference to a secret, never the key itself
    enabled      INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL
);
"""

# Schema creation is cached per database path so we don't re-run DDL on every
# connection. Keyed by path so tests can point at isolated temp databases.
_SCHEMA_READY: Dict[str, bool] = {}
_schema_lock = threading.Lock()


def _db_path() -> str:
    """Resolve the platform database path (env override for tests/deploys)."""
    return os.getenv("AGENTFACTORY_DB_PATH", DEFAULT_DB_PATH)


def init_db(db_path: Optional[str] = None) -> None:
    """Create schema v2 tables if they don't exist (idempotent)."""
    path = db_path or _db_path()
    with _schema_lock:
        if _SCHEMA_READY.get(path):
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        conn = sqlite3.connect(path)
        try:
            conn.executescript(_SCHEMA_SQL)
            conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            conn.commit()
            _SCHEMA_READY[path] = True
        finally:
            conn.close()


def get_db() -> sqlite3.Connection:
    """Open a connection to the platform database (schema ensured)."""
    init_db()
    conn = sqlite3.connect(_db_path(), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

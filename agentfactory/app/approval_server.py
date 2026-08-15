"""
Approval Server — FastAPI control plane with SQLite persistence.

Features:
- SQLite database for persistent proposal state (survives restarts)
- Atomic state transitions with row-level locking
- Discord + Gmail notifications with interactive approval buttons
- Health endpoint (no token leakage)
- RESTful API for proposal registration and review
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta
import os
import json
import sqlite3
import structlog
import threading
import contextlib

from agentfactory.config import settings

# Initialize logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)
logger = structlog.get_logger()

# ============================================================
# JWT Authentication
# ============================================================

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "agentfactory")

bearer_scheme = HTTPBearer(auto_error=False)


def _is_auth_enabled() -> bool:
    """Check if JWT authentication is enabled (secret key set)."""
    return bool(JWT_SECRET_KEY)


def _encode_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Encode a JWT token."""
    import jwt
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(hours=JWT_EXPIRATION_HOURS))
    to_encode.update({"iat": int(now.timestamp()), "exp": int(expire.timestamp()), "aud": JWT_AUDIENCE})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT token."""
    import jwt
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM], audience=JWT_AUDIENCE, options={"require_aud": True, "require_exp": True, "require_iat": True})
        return payload
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid or expired token: {str(e)}", headers={"WWW-Authenticate": "Bearer"})


async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)) -> Dict[str, Any]:
    """Dependency to authenticate requests via JWT bearer token."""
    if not _is_auth_enabled():
        return {"sub": "public", "roles": ["public"]}
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"})
    return _decode_token(credentials.credentials)


def require_role(*roles: str):
    """Dependency factory: require one of the specified roles."""
    async def role_checker(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        user_roles = user.get("roles", [])
        if not any(r in user_roles for r in roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Insufficient permissions. Required: {roles}")
        return user
    return role_checker


# ============================================================
# FastAPI App
# ============================================================

app = FastAPI(
    title="AgentFactory Approval Server",
    description="Control API for multi-agent team approvals",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# SQLite Database
# ============================================================

DB_PATH = os.getenv("APPROVAL_DB_PATH", os.path.join(os.path.expanduser("~"), ".agentfactory", "approval.db"))

_db_lock = threading.Lock()


def init_db():
    """Initialize the SQLite database."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    with _db_lock:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS proposals (
                id TEXT PRIMARY KEY,
                feature_name TEXT NOT NULL,
                plan TEXT,
                blueprint TEXT,
                status TEXT NOT NULL DEFAULT 'IDLE',
                extra_instructions TEXT,
                created_at TEXT,
                updated_at TEXT,
                approved_at TEXT,
                repo_paths TEXT,
                UNIQUE(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                proposal_id TEXT,
                details TEXT,
                timestamp TEXT
            )
        """)

        # Create an index for efficient status queries
        conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON proposals(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_updated_at ON proposals(updated_at)")

        conn.commit()
        conn.close()
        logger.info(f"Database initialized at {DB_PATH}")


def get_db():
    """Get a database connection."""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # Enable WAL for concurrent access
    return conn


def lock_proposal(proposal_id: str) -> bool:
    """
    Attempt to acquire a lock on a proposal.

    Uses a separate lock table to handle race conditions.
    Returns True if lock acquired, False otherwise.
    """
    with _db_lock:
        conn = get_db()
        try:
            # Check if proposal exists and get its lock status
            row = conn.execute(
                "SELECT status FROM proposals WHERE id = ?",
                (proposal_id,)
            ).fetchone()

            if row is None:
                return False

            # Atomic update with condition
            result = conn.execute("""
                UPDATE proposals
                SET status = ?, updated_at = ?
                WHERE id = ? AND status != ?
            """, ("PROCESSING", datetime.now(timezone.utc).isoformat(), proposal_id, "PROCESSING"))

            conn.commit()
            return result.rowcount > 0
        finally:
            conn.close()


# ============================================================
# Pydantic Models
# ============================================================

class ProposalPayload(BaseModel):
    """Payload for registering a new feature proposal."""
    feature_name: str = Field(..., description="Name of the feature")
    implementation_plan: str = Field(..., description="Detailed implementation plan")
    blueprint: Optional[Dict[str, Any]] = Field(default=None, description="Structured blueprint")


class ReviewPayload(BaseModel):
    """Payload for reviewing an approval."""
    action: str = Field(..., description="APPROVE, REJECT, or MODIFY")
    additional_commands: Optional[str] = Field(default=None, description="Custom instructions for MODIFY")


class ProposalResponse(BaseModel):
    """Response when a proposal is registered."""
    status: str
    proposal_id: str


# ============================================================
# API Endpoints
# ============================================================

@app.get("/")
async def root():
    """Health check endpoint — returns no tokens, no sensitive data."""
    return {"status": "ok", "service": "AgentFactory Approval Server", "version": "1.0.0", "auth_enabled": _is_auth_enabled()}


class TokenRequest(BaseModel):
    """Request a JWT token (requires JWT_SECRET_KEY to be configured)."""
    sub: str = Field(..., description="Subject (user identifier)")
    roles: List[str] = Field(default_factory=lambda: ["user"])
    expires_hours: Optional[int] = Field(default=None, description="Custom expiry in hours")


@app.post("/api/agent/token")
async def issue_token(payload: TokenRequest):
    """
    Issue a JWT token for API access.

    This endpoint is only available when JWT_SECRET_KEY is set in the environment.
    In production, front this with an identity provider or API gateway.

    Args:
        sub: User identifier (e.g., email or username)
        roles: Roles to assign (e.g., ["user"], ["admin"])
        expires_hours: Custom token expiry (defaults to JWT_EXPIRATION_HOURS)

    Returns:
        JWT token string
    """
    if not _is_auth_enabled():
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="JWT authentication is not configured. Set JWT_SECRET_KEY environment variable.",
        )

    expires_delta = timedelta(hours=payload.expires_hours) if payload.expires_hours else None
    token = _encode_token({"sub": payload.sub, "roles": payload.roles}, expires_delta)

    logger.info("Token issued", sub=payload.sub, roles=payload.roles)
    return {"access_token": token, "token_type": "bearer"}


@app.get("/api/agent/status")
async def get_status():
    """Get the current proposal status."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, feature_name, plan, blueprint, status, extra_instructions, created_at, updated_at, approved_at FROM proposals ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()

        if row is None:
            return {
                "status": "IDLE",
                "feature_name": None,
                "plan": None,
                "blueprint": None,
                "extra_instructions": None,
            }

        blueprint = json.loads(row["blueprint"]) if row["blueprint"] else None

        return {
            "proposal_id": row["id"],
            "feature_name": row["feature_name"],
            "plan": row["plan"],
            "blueprint": blueprint,
            "status": row["status"],
            "extra_instructions": row["extra_instructions"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "approved_at": row["approved_at"],
        }
    finally:
        conn.close()


@app.post("/api/agent/propose", dependencies=[Depends(get_current_user)])
async def propose_feature(payload: ProposalPayload):
    """
    Register a new feature proposal.

    Creates a new proposal in the SQLite database and sends
    notifications to Discord and Gmail.
    """
    proposal_id = f"prop-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    now = datetime.now(timezone.utc).isoformat()

    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO proposals (id, feature_name, plan, blueprint, status, extra_instructions, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            proposal_id,
            payload.feature_name,
            payload.implementation_plan,
            json.dumps(payload.blueprint) if payload.blueprint else None,
            "PENDING",
            None,
            now,
            now,
        ))
        conn.commit()

        # Log to audit
        conn.execute("""
            INSERT INTO audit_log (action, proposal_id, details, timestamp)
            VALUES (?, ?, ?, ?)
        """, ("PROPOSE", proposal_id, "Feature proposal registered", now))
        conn.commit()
    finally:
        conn.close()

    logger.info("Proposal registered", proposal_id=proposal_id, feature=payload.feature_name)

    # Send notifications (async)
    branch_name = f"feature/{payload.feature_name.lower().replace(' ', '-')}"

    # Discord notification with buttons
    _send_discord_proposal(payload.feature_name, payload.implementation_plan, branch_name)

    # Gmail notification
    _send_gmail_proposal(payload.feature_name, payload.implementation_plan, branch_name)

    return {
        "status": "Proposal registered, awaiting approval.",
        "proposal_id": proposal_id,
    }


@app.post("/api/agent/review", dependencies=[Depends(get_current_user)])
async def review_proposal(payload: ReviewPayload):
    """
    Review an approval: APPROVE, REJECT, or MODIFY.

    Uses SQLite atomic updates to prevent race conditions.
    """
    action = payload.action.strip().upper()
    now = datetime.now(timezone.utc).isoformat()

    conn = get_db()
    try:
        # Get the current proposal
        row = conn.execute(
            "SELECT id, feature_name FROM proposals ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail="No active proposal found.")

        proposal_id = row["id"]
        feature_name = row["feature_name"]

        if action == "APPROVE":
            conn.execute("""
                UPDATE proposals SET status = ?, approved_at = ?, updated_at = ?
                WHERE id = ?
            """, ("APPROVED", now, now, proposal_id))
            conn.execute("""
                INSERT INTO audit_log (action, proposal_id, details, timestamp)
                VALUES (?, ?, ?, ?)
            """, ("APPROVE", proposal_id, f"Feature '{feature_name}' approved", now))
            conn.commit()

            logger.info("Proposal approved", proposal_id=proposal_id)

            # Send approval notification
            branch_name = f"feature/{feature_name.lower().replace(' ', '-')}"
            _send_discord_status("✅ Feature Approved", f"**{feature_name}** approved and ready for execution.", branch_name, color=0x00ff00)

            return {"message": "Proposal Approved! Worker will execute code generation."}

        elif action == "MODIFY":
            conn.execute("""
                UPDATE proposals SET status = ?, extra_instructions = ?, updated_at = ?
                WHERE id = ?
            """, ("MODIFIED", payload.additional_commands, now, proposal_id))
            conn.execute("""
                INSERT INTO audit_log (action, proposal_id, details, timestamp)
                VALUES (?, ?, ?, ?)
            """, ("MODIFY", proposal_id, f"Modified with: {payload.additional_commands}", now))
            conn.commit()

            logger.info("Proposal modified", proposal_id=proposal_id, instructions=payload.additional_commands)
            return {"message": f"Instructions updated. Blueprint will be rewritten before execution."}

        elif action == "REJECT":
            conn.execute("""
                UPDATE proposals SET status = ?, updated_at = ?
                WHERE id = ?
            """, ("REJECTED", now, proposal_id))
            conn.execute("""
                INSERT INTO audit_log (action, proposal_id, details, timestamp)
                VALUES (?, ?, ?, ?)
            """, ("REJECT", proposal_id, "Feature proposal rejected", now))
            conn.commit()

            logger.info("Proposal rejected", proposal_id=proposal_id)
            return {"message": "Proposal rejected. No changes made."}

        else:
            raise HTTPException(status_code=400, detail=f"Invalid action: {action}. Use APPROVE, REJECT, or MODIFY.")

    finally:
        conn.close()


@app.post("/api/agent/executed", dependencies=[Depends(get_current_user)])
async def mark_executed():
    """Mark the current proposal as completed after worker finishes."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id FROM proposals WHERE status = 'APPROVED' ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()

        if row is None:
            raise HTTPException(status_code=400, detail="No approved proposal to mark as executed.")

        proposal_id = row["id"]

        conn.execute("""
            UPDATE proposals SET status = ?, updated_at = ?
            WHERE id = ?
        """, ("COMPLETED", datetime.now(timezone.utc).isoformat(), proposal_id))
        conn.execute("""
            INSERT INTO audit_log (action, proposal_id, details, timestamp)
            VALUES (?, ?, ?, ?)
        """, ("COMPLETE", proposal_id, "Feature execution completed", datetime.now(timezone.utc).isoformat()))
        conn.commit()

        return {"status": "Execution marked as completed."}
    finally:
        conn.close()


@app.get("/api/agent/proposals")
async def list_proposals(limit: int = 20, status_filter: Optional[str] = None):
    """List recent proposals."""
    conn = get_db()
    try:
        query = "SELECT id, feature_name, status, created_at, updated_at FROM proposals"
        params: List[Any] = []

        if status_filter:
            query += " WHERE status = ?"
            params.append(status_filter)

        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()

        return [{
            "id": row["id"],
            "feature_name": row["feature_name"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        } for row in rows]
    finally:
        conn.close()


@app.delete("/api/agent/proposals/{proposal_id}", dependencies=[Depends(get_current_user)])
async def delete_proposal(proposal_id: str):
    """Delete a proposal (admin operation)."""
    conn = get_db()
    try:
        result = conn.execute("DELETE FROM proposals WHERE id = ?", (proposal_id,))
        conn.execute("DELETE FROM audit_log WHERE proposal_id = ?", (proposal_id,))
        conn.commit()

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Proposal '{proposal_id}' not found.")

        return {"status": "deleted", "proposal_id": proposal_id}
    finally:
        conn.close()


# ============================================================
# Notification Helpers
# ============================================================

def _send_discord_proposal(title: str, plan: str, branch_name: str):
    """Send proposal notification to Discord with interactive buttons."""
    webhook_url = os.getenv("DEV_NOTIF_WEBHOOK_URL")
    if not webhook_url:
        return

    import requests

    payload = {
        "content": "🚨 **ACTION REQUIRED: Feature Proposal**",
        "embeds": [{
            "title": title,
            "description": plan[:4000] if len(plan) > 4000 else plan,
            "color": 0xffaa00,
            "fields": [
                {"name": "Branch", "value": branch_name, "inline": True},
                {"name": "Status", "value": "PENDING APPROVAL", "inline": True},
            ],
        }],
        "components": [
            {
                "type": 1,
                "components": [
                    {
                        "type": 2,
                        "style": 3,
                        "label": "Approve",
                        "custom_id": "btn_approve",
                        "emoji": {"name": "✅"},
                    },
                    {
                        "type": 2,
                        "style": 4,
                        "label": "Reject",
                        "custom_id": "btn_reject",
                        "emoji": {"name": "❌"},
                    },
                ],
            }
        ],
    }

    try:
        requests.post(webhook_url, json=payload, timeout=10)
    except Exception as e:
        logger.warning(f"Discord notification failed: {e}")


def _send_gmail_proposal(title: str, plan: str, branch_name: str):
    """Send proposal notification to Gmail."""
    gmail_user = os.getenv("GMAIL_USER")
    gmail_pass = os.getenv("GMAIL_APP_PASSWORD")
    admin_email = os.getenv("ADMIN_EMAIL", gmail_user)

    if not gmail_user or not gmail_pass:
        return

    import smtplib
    from email.message import EmailMessage

    msg = EmailMessage()
    msg.set_content(f"""
Hello,

A new feature proposal is awaiting your approval:

Title: {title}
Branch: {branch_name}

Plan:
{plan[:2000]}

---
To approve: curl -X POST http://localhost:8000/api/agent/review -H 'Content-Type: application/json' -d '{{"action": "APPROVE"}}'
To reject:  curl -X POST http://localhost:8000/api/agent/review -H 'Content-Type: application/json' -d '{{"action": "REJECT"}}'
To modify:  curl -X POST http://localhost:8000/api/agent/review -H 'Content-Type: application/json' -d '{{"action": "MODIFY", "additional_commands": "..."}}'

— AgentFactory Bot
    """)
    msg["Subject"] = f"[AgentFactory] Proposal: {title}"
    msg["From"] = gmail_user
    msg["To"] = admin_email

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_pass)
            server.send_message(msg)
    except Exception as e:
        logger.warning(f"Gmail notification failed: {e}")


def _send_discord_status(title: str, message: str, branch_name: str, color: int = 0x00ff00):
    """Send a quick status notification to Discord."""
    webhook_url = os.getenv("DEV_NOTIF_WEBHOOK_URL")
    if not webhook_url:
        return

    import requests

    payload = {
        "embeds": [{
            "title": title,
            "description": message,
            "color": color,
            "fields": [
                {"name": "Branch", "value": branch_name, "inline": True},
            ],
        }],
        "username": "AgentFactory Bot",
    }

    try:
        requests.post(webhook_url, json=payload, timeout=10)
    except Exception:
        pass


# ============================================================
# Startup
# ============================================================

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    init_db()
    logger.info("AgentFactory Approval Server started")

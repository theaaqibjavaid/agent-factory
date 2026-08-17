"""
Platform auth router — signup, login, refresh (rotation), logout, and OAuth
(Google/GitHub). The ``/me`` profile endpoint lives in ``routers/users.py``.

On signup a default workspace is created with an owner membership, a starter
agent, and default user settings (Phase 1, task 1.4).
"""

import os
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agentfactory.app import db, security
from agentfactory.app.deps import get_current_user, user_payload

router = APIRouter(prefix="/auth", tags=["auth"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PASSWORD_MIN = 8


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------

class SignupRequest(BaseModel):
    email: str = Field(..., description="Email address")
    password: str = Field(..., min_length=_PASSWORD_MIN, description="Password (min 8 chars)")
    name: Optional[str] = Field(default=None, description="Display name")


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "workspace"


def _get_user_by_email(email: str) -> Optional[dict]:
    conn = db.get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _get_user_by_oauth(provider: str, provider_sub: str) -> Optional[dict]:
    conn = db.get_db()
    try:
        row = conn.execute(
            "SELECT u.* FROM users u JOIN oauth_accounts o ON o.user_id = u.id "
            "WHERE o.provider = ? AND o.provider_sub = ?",
            (provider, provider_sub),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _link_oauth(user_id: str, provider: str, provider_sub: str) -> None:
    conn = db.get_db()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO oauth_accounts (id, user_id, provider, provider_sub) VALUES (?, ?, ?, ?)",
            (uuid.uuid4().hex, user_id, provider, str(provider_sub)),
        )
        conn.commit()
    finally:
        conn.close()


def _create_default_workspace(user_id: str, email: str) -> str:
    """Create 'My Workspace' + owner membership + starter agent + user settings."""
    now = _now_iso()
    workspace_id = uuid.uuid4().hex
    slug = f"{_slugify((email or 'user').split('@')[0])}-{uuid.uuid4().hex[:6]}"

    conn = db.get_db()
    try:
        conn.execute(
            "INSERT INTO workspaces (id, name, slug, owner_user_id, settings, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (workspace_id, "My Workspace", slug, user_id, "{}", now),
        )
        conn.execute(
            "INSERT INTO workspace_members (workspace_id, user_id, role, created_at) VALUES (?, ?, ?, ?)",
            (workspace_id, user_id, "owner", now),
        )
        # Starter agent — a web research assistant using built-in tools.
        conn.execute(
            """
            INSERT INTO agents (id, workspace_id, name, rank, role_description,
                                system_instructions, model_preferences, tools, skills,
                                mcp_servers, temperature, max_budget_usd_per_day,
                                hitl_mode, max_iterations, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uuid.uuid4().hex,
                workspace_id,
                "Research Assistant",
                "Junior",
                "Searches the web and summarizes findings with citations",
                "You are a research agent. Search the web for the latest information and "
                "summarize findings with source citations.",
                '["gemini-2.5-flash", "gpt-4o-mini"]',
                '["web_search", "web_fetch", "web_scrape_links"]',
                "[]",
                "[]",
                0.2,
                5.0,
                "auto",
                20,
                "idle",
                now,
                now,
            ),
        )
        conn.execute(
            "INSERT INTO user_settings (user_id, theme, fonts, updated_at) VALUES (?, ?, ?, ?)",
            (user_id, "light", "{}", now),
        )
        conn.commit()
    finally:
        conn.close()
    return workspace_id


def _issue_tokens_for(user: dict) -> dict:
    tokens = security.create_token_pair(user["id"])
    tokens["user"] = user_payload(user)
    return tokens


# --------------------------------------------------------------------------
# Email/password auth
# --------------------------------------------------------------------------

@router.post("/signup", status_code=201)
def signup(payload: SignupRequest):
    email = payload.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="Invalid email address")
    if _get_user_by_email(email) is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    now = _now_iso()
    user_id = uuid.uuid4().hex
    conn = db.get_db()
    try:
        conn.execute(
            "INSERT INTO users (id, email, password_hash, name, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, email, security.hash_password(payload.password), payload.name or email.split("@")[0], now, now),
        )
        conn.commit()
    finally:
        conn.close()

    _create_default_workspace(user_id, email)
    return _issue_tokens_for({"id": user_id, "email": email, "name": payload.name or email.split("@")[0], "avatar_url": None, "created_at": now})


@router.post("/login")
def login(payload: LoginRequest):
    email = payload.email.strip().lower()
    user = _get_user_by_email(email)
    if user is None or not security.verify_password(user.get("password_hash"), payload.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return _issue_tokens_for(user)


@router.post("/refresh")
def refresh(payload: RefreshRequest):
    rotated = security.rotate_refresh_token(payload.refresh_token)
    if rotated is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    conn = db.get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (rotated["user_id"],)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=401, detail="User no longer exists")
    tokens = {
        "access_token": security.create_access_token(row["id"]),
        "refresh_token": rotated["refresh_token"],
        "token_type": "bearer",
        "user": user_payload(dict(row)),
    }
    return tokens


@router.post("/logout")
def logout(payload: LogoutRequest, user: dict = Depends(get_current_user)):
    security.revoke_refresh_token(payload.refresh_token)
    return {"status": "logged out"}


# --------------------------------------------------------------------------
# OAuth (Google / GitHub)
# --------------------------------------------------------------------------

_OAUTH_PROVIDERS = {"google", "github"}


def _oauth_credentials(provider: str):
    prefix = provider.upper()
    client_id = os.getenv(f"{prefix}_CLIENT_ID", "")
    client_secret = os.getenv(f"{prefix}_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise HTTPException(status_code=400, detail=f"{provider} OAuth is not configured on this server")
    return client_id, client_secret


def _redirect_uri(provider: str) -> str:
    base = os.getenv("AGENTFACTORY_APP_URL", "http://localhost:8000").rstrip("/")
    return f"{base}/api/v1/auth/oauth/{provider}/callback"


@router.get("/oauth/{provider}")
def oauth_authorize(provider: str):
    """Return the provider authorize URL (start the OAuth dance)."""
    if provider not in _OAUTH_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
    client_id, _ = _oauth_credentials(provider)
    state = security.encode_oauth_state()
    redirect_uri = _redirect_uri(provider)

    if provider == "google":
        url = (
            "https://accounts.google.com/o/oauth2/v2/auth"
            f"?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code"
            "&scope=openid%20email%20profile&state=" + state
        )
    else:  # github
        url = (
            "https://github.com/login/oauth/authorize"
            f"?client_id={client_id}&redirect_uri={redirect_uri}&scope=read:user%20user:email&state=" + state
        )
    return {"authorize_url": url, "provider": provider}


@router.get("/oauth/{provider}/callback")
def oauth_callback(provider: str, code: str, state: str):
    if provider not in _OAUTH_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
    try:
        security.decode_oauth_state(state)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    client_id, client_secret = _oauth_credentials(provider)
    redirect_uri = _redirect_uri(provider)

    if provider == "google":
        profile = _exchange_google(code, redirect_uri, client_id, client_secret)
    else:
        profile = _exchange_github(code, redirect_uri, client_id, client_secret)

    user = _oauth_login(provider, profile)
    return _issue_tokens_for(user)


def _exchange_google(code: str, redirect_uri: str, client_id: str, client_secret: str) -> dict:
    token_resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    token_resp.raise_for_status()
    access_token = token_resp.json()["access_token"]

    user_resp = requests.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    user_resp.raise_for_status()
    data = user_resp.json()
    return {
        "provider_sub": str(data.get("id") or data.get("email")),
        "email": (data.get("email") or "").lower(),
        "name": data.get("name"),
        "avatar_url": data.get("picture"),
    }


def _exchange_github(code: str, redirect_uri: str, client_id: str, client_secret: str) -> dict:
    token_resp = requests.post(
        "https://github.com/login/oauth/access_token",
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        },
        headers={"Accept": "application/json"},
        timeout=10,
    )
    token_resp.raise_for_status()
    access_token = token_resp.json()["access_token"]

    user_resp = requests.get(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=10,
    )
    user_resp.raise_for_status()
    data = user_resp.json()
    return {
        "provider_sub": str(data.get("id")),
        "email": (data.get("email") or "").lower(),
        "name": data.get("name"),
        "avatar_url": data.get("avatar_url"),
    }


def _oauth_login(provider: str, profile: dict) -> dict:
    """Find or create a user for an OAuth profile, then link the account."""
    provider_sub = profile.get("provider_sub")
    user = _get_user_by_oauth(provider, provider_sub)

    if user is None:
        email = profile.get("email") or ""
        if email:
            user = _get_user_by_email(email)
        if user is None:
            now = _now_iso()
            user_id = uuid.uuid4().hex
            conn = db.get_db()
            try:
                conn.execute(
                    "INSERT INTO users (id, email, password_hash, name, avatar_url, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (user_id, email or None, None, profile.get("name"), profile.get("avatar_url"), now, now),
                )
                conn.commit()
            finally:
                conn.close()
            user = {"id": user_id, "email": email or None, "name": profile.get("name"),
                    "avatar_url": profile.get("avatar_url"), "created_at": now}
            _create_default_workspace(user_id, email or f"{provider}-{provider_sub}")

    _link_oauth(user["id"], provider, provider_sub)
    return user

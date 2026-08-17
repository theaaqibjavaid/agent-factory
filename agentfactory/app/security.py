"""
Platform security — password hashing, access JWTs, refresh-token rotation.

- Passwords: argon2id via ``argon2-cffi`` (config from env, see docs/env-vars.md).
- Access tokens: short-lived JWT (default 15 min) signed with
  ``AGENTFACTORY_JWT_SECRET`` (falls back to ``JWT_SECRET_KEY``).
- Refresh tokens: opaque, random, stored in SQLite with rotation + revocation
  (replaying a rotated token is rejected). Secrets/config are read lazily from
  the environment so tests can swap them per-request.
"""

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from agentfactory.app import db

ACCESS_AUDIENCE = "agentfactory-platform"
OAUTH_STATE_AUDIENCE = "agentfactory-oauth-state"

_ph = PasswordHasher()


# --------------------------------------------------------------------------
# Config (lazy env reads — swappable in tests)
# --------------------------------------------------------------------------

def _secret() -> str:
    return os.getenv("AGENTFACTORY_JWT_SECRET", os.getenv("JWT_SECRET_KEY", ""))


def _access_expiry_minutes() -> int:
    return int(os.getenv("AGENTFACTORY_ACCESS_TOKEN_MINUTES", "15"))


def _refresh_expiry_days() -> int:
    return int(os.getenv("AGENTFACTORY_REFRESH_TOKEN_DAYS", "7"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


# --------------------------------------------------------------------------
# Passwords (argon2id)
# --------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash a plaintext password with argon2id."""
    return _ph.hash(password)


def verify_password(password_hash: Optional[str], password: str) -> bool:
    """Verify a password against its stored hash. Returns False on any failure."""
    if not password_hash:
        return False
    try:
        return _ph.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        # InvalidHashError: stored value is not an argon2 hash at all
        # (corrupt data or a foreign hash) — treat as a failed verification.
        return False


# --------------------------------------------------------------------------
# Access tokens (JWT)
# --------------------------------------------------------------------------

def create_access_token(
    user_id: str,
    expires_minutes: Optional[int] = None,
    workspace_ids: Optional[list] = None,
) -> str:
    """Issue a short-lived access JWT for a user."""
    import jwt

    now = _now()
    payload: Dict[str, Any] = {
        "sub": user_id,
        "type": "access",
        "aud": ACCESS_AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes or _access_expiry_minutes())).timestamp()),
    }
    if workspace_ids:
        payload["workspaces"] = workspace_ids
    return jwt.encode(payload, _secret(), algorithm="HS256")


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode + validate an access JWT. Raises jwt.PyJWTError on failure."""
    import jwt

    return jwt.decode(
        token,
        _secret(),
        algorithms=["HS256"],
        audience=ACCESS_AUDIENCE,
        options={"require_aud": True, "require_exp": True, "require_iat": True},
    )


def encode_oauth_state() -> str:
    """Sign a short-lived state value for the OAuth authorization dance."""
    import jwt

    now = _now()
    payload = {
        "type": "oauth_state",
        "aud": OAUTH_STATE_AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=10)).timestamp()),
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def decode_oauth_state(state: str) -> Dict[str, Any]:
    """Validate an OAuth state value. Raises jwt.PyJWTError on failure."""
    import jwt

    return jwt.decode(
        state,
        _secret(),
        algorithms=["HS256"],
        audience=OAUTH_STATE_AUDIENCE,
        options={"require_aud": True, "require_exp": True, "require_iat": True},
    )


# --------------------------------------------------------------------------
# Refresh tokens (opaque, revocable, rotated)
# --------------------------------------------------------------------------

def issue_refresh_token(user_id: str) -> str:
    """Create a new refresh token for a user."""
    jti = secrets.token_urlsafe(32)
    now = _now()
    expires = now + timedelta(days=_refresh_expiry_days())
    conn = db.get_db()
    try:
        conn.execute(
            "INSERT INTO refresh_tokens (jti, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (jti, user_id, now.isoformat(), expires.isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
    return jti


def rotate_refresh_token(jti: str) -> Optional[Dict[str, Any]]:
    """
    Validate a refresh token and rotate it.

    The presented token is revoked and a fresh token is issued for the same
    user. Replays of already-rotated/revoked tokens are rejected (returns None).
    """
    conn = db.get_db()
    try:
        row = conn.execute("SELECT * FROM refresh_tokens WHERE jti = ?", (jti,)).fetchone()
        if row is None or row["revoked_at"] or row["replaced_by"]:
            return None
        if datetime.fromisoformat(row["expires_at"]) < _now():
            return None

        new_jti = secrets.token_urlsafe(32)
        now = _now()
        expires = now + timedelta(days=_refresh_expiry_days())
        conn.execute(
            "UPDATE refresh_tokens SET revoked_at = ?, replaced_by = ? WHERE jti = ?",
            (now.isoformat(), new_jti, jti),
        )
        conn.execute(
            "INSERT INTO refresh_tokens (jti, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (new_jti, row["user_id"], now.isoformat(), expires.isoformat()),
        )
        conn.commit()
        return {
            "refresh_token": new_jti,
            "user_id": row["user_id"],
            "expires_at": expires.isoformat(),
        }
    finally:
        conn.close()


def revoke_refresh_token(jti: str) -> None:
    """Revoke a refresh token (logout)."""
    conn = db.get_db()
    try:
        conn.execute(
            "UPDATE refresh_tokens SET revoked_at = ? WHERE jti = ?",
            (_now_iso(), jti),
        )
        conn.commit()
    finally:
        conn.close()


def create_token_pair(user_id: str) -> Dict[str, str]:
    """Issue a full token pair (access + refresh)."""
    return {
        "access_token": create_access_token(user_id),
        "refresh_token": issue_refresh_token(user_id),
        "token_type": "bearer",
    }

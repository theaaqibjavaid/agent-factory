"""
Encryption-at-rest (Phase 8.1 — security backlog S-9).

Conversations, facts, plans, and approval data are stored in SQLite. When the
operator sets ``AGENTFACTORY_ENCRYPTION_KEY`` (a Fernet key), sensitive columns
are encrypted before they hit disk and transparently decrypted on read.

Design:

- **Opt-in.** Without the env var, every helper is a no-op that returns the
  input unchanged, so existing installs and tests behave exactly as before.
- **Backward compatible.** ``decrypt_text`` auto-detects Fernet tokens
  (they always start with ``gAAAA``) and passes legacy plaintext through, so
  enabling encryption on an existing database does not require a migration —
  old rows keep working and new rows get encrypted.
- **Key derivation.** Accepts a raw Fernet key (44-char urlsafe base64, from
  ``Fernet.generate_key()``) or any string secret, which is stretched with
  PBKDF2-HMAC-SHA256.

Generate a key with::

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import base64
import hashlib
import os
import threading
from typing import Optional

_FERNET_PREFIX = "gAAAA"
_ENV_KEY = "AGENTFACTORY_ENCRYPTION_KEY"


class EncryptionError(RuntimeError):
    """Raised when a stored value cannot be decrypted (bad/missing key)."""


_lock = threading.Lock()
_cached_fernet = None
_cached_raw_key: Optional[str] = None


def _derive_fernet(raw_key: str):
    """Build a Fernet instance from a raw key, stretching arbitrary secrets."""
    from cryptography.fernet import Fernet, InvalidToken

    try:
        # Raw Fernet keys are 32 bytes urlsafe-b64 (44 chars). Use directly.
        decoded = base64.urlsafe_b64decode(raw_key.encode("ascii") + b"=" * (-len(raw_key) % 4))
        if len(decoded) == 32:
            return Fernet(raw_key.encode("ascii")), InvalidToken
    except Exception:  # noqa: BLE001 — fall through to derivation for any non-Fernet input
        pass

    derived = base64.urlsafe_b64encode(
        hashlib.pbkdf2_hmac("sha256", raw_key.encode("utf-8"), b"agentfactory-at-rest", 200_000)
    )
    return Fernet(derived), InvalidToken


def get_fernet():
    """Return the process-wide Fernet instance, or None when no key is configured."""
    global _cached_fernet, _cached_raw_key
    raw_key = os.getenv(_ENV_KEY, "").strip()
    if not raw_key:
        return None
    with _lock:
        if _cached_fernet is not None and raw_key == _cached_raw_key:
            return _cached_fernet
        _cached_raw_key = raw_key
        _cached_fernet, _ = _derive_fernet(raw_key)
        return _cached_fernet


def encryption_enabled() -> bool:
    """True when AGENTFACTORY_ENCRYPTION_KEY is set (writes will be encrypted)."""
    return get_fernet() is not None


def reset() -> None:
    """Clear the cached Fernet instance (mainly for tests that swap the env var)."""
    global _cached_fernet, _cached_raw_key
    _cached_fernet = None
    _cached_raw_key = None


def encrypt_text(plaintext: str) -> str:
    """Encrypt a string. Raises EncryptionError when no key is configured."""
    fernet = get_fernet()
    if fernet is None:
        raise EncryptionError(
            f"{_ENV_KEY} is not set — cannot encrypt. Set it to enable encryption-at-rest."
        )
    return fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_text(stored: str) -> str:
    """
    Decrypt a stored value. Fernet tokens are decrypted; legacy plaintext
    passes through unchanged so enabling encryption never breaks old rows.
    """
    if not stored or not stored.startswith(_FERNET_PREFIX):
        return stored
    fernet = get_fernet()
    if fernet is None:
        raise EncryptionError(
            f"Stored value is encrypted but {_ENV_KEY} is not set — set the same key "
            "used when the data was written."
        )
    try:
        return fernet.decrypt(stored.encode("ascii")).decode("utf-8")
    except Exception as e:  # noqa: BLE001 — wrap cryptography's InvalidToken
        raise EncryptionError(
            f"Failed to decrypt value (wrong AGENTFACTORY_ENCRYPTION_KEY?): {e}"
        ) from e


def encrypt_field(value: Optional[str]) -> Optional[str]:
    """Encrypt a nullable string column. No-op when encryption is disabled."""
    if value is None or not encryption_enabled():
        return value
    return encrypt_text(value)


def decrypt_field(value: Optional[str]) -> Optional[str]:
    """Decrypt a nullable string column. Plaintext (legacy) values pass through."""
    if value is None:
        return None
    return decrypt_text(value)

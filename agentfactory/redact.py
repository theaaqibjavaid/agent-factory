"""
Log/key hygiene (Phase 8.2 — security backlog S-10).

Provider error messages and exception text sometimes echo API keys back
(e.g. ``sk-...`` prefixes, ``AIza...`` Google keys, Bearer tokens). This module
scrubs common secret shapes before a string is logged or persisted.

``redact_secrets`` is intentionally conservative: patterns match only
high-entropy shapes, and any match is replaced with ``<redacted>`` so the
original value never leaks through logs, run errors, or observability payloads.
"""

import re
from typing import Optional

_REDACTED = "<redacted>"

# Provider API keys / tokens with recognizable high-entropy prefixes.
_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),             # OpenAI / Anthropic style
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),            # Google (Gemini) keys
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                  # AWS access key id
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),      # Slack tokens
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),        # GitHub tokens
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{10,}\b", re.IGNORECASE),  # Bearer tokens
    re.compile(r"(?i)\bapi[_-]?key\b[\"']?\s*[:=]\s*[\"'][^\"']{6,}[\"']"),
    re.compile(r"(?i)\b(?:password|passwd|secret|token)\b[\"']?\s*[:=]\s*[\"'][^\"']{6,}[\"']"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9._-]{10,}\b"),  # JWT (compact form)
]


def redact_secrets(text: Optional[str]) -> str:
    """Return ``text`` with known secret shapes replaced by ``<redacted>``."""
    if not text:
        return text or ""
    result = text
    for pattern in _PATTERNS:
        result = pattern.sub(_REDACTED, result)
    return result

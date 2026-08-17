"""
Rate limiting for sensitive endpoints (Phase 7.1 — closes security backlog S-8).

A small in-memory sliding-window limiter keyed by ``(scope, client_ip)``.
Auth endpoints (signup/login/refresh/...) are limited per IP to blunt
credential-stuffing and account-enumeration attacks. Configurable:

- ``AGENTFACTORY_RATE_LIMIT_AUTH`` — max requests per minute per IP on the
  auth surface (default 20; set ``0`` to disable).

Deliberately dependency-free (stdlib only): self-hosters behind a single
process get a real guard without adding ``slowapi``; multi-process deployments
should put a proper reverse-proxy limiter in front instead (documented in
``docs/security.md`` and ``docs/self-host.md``).
"""

import os
import threading
import time
from typing import Callable, Dict, List, Tuple

from fastapi import HTTPException, Request, status


def _auth_limit_per_minute() -> int:
    """Auth rate limit (requests/minute/IP) from env; 0 disables."""
    raw = os.getenv("AGENTFACTORY_RATE_LIMIT_AUTH", "20")
    try:
        value = int(raw)
    except ValueError:
        return 20
    return max(0, value)


def _client_ip(request: Request) -> str:
    """Best-effort client IP: X-Forwarded-For first hop, else the socket peer."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    peer = request.client
    return peer.host if peer else "unknown"


class _SlidingWindow:
    """Thread-safe sliding-window bucket per (scope, key)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: Dict[Tuple[str, str], List[float]] = {}

    def allow(self, scope: str, key: str, limit: int, window_seconds: float = 60.0) -> Tuple[bool, float]:
        """Record one request; return (allowed, seconds_until_retry)."""
        now = time.monotonic()
        bucket_key = (scope, key)
        with self._lock:
            timestamps = [t for t in self._buckets.get(bucket_key, []) if now - t < window_seconds]
            if len(timestamps) >= limit:
                self._buckets[bucket_key] = timestamps
                retry_after = window_seconds - (now - timestamps[0])
                return False, max(1.0, round(retry_after, 1))
            timestamps.append(now)
            self._buckets[bucket_key] = timestamps
            return True, 0.0


_windows = _SlidingWindow()


def reset() -> None:
    """Drop all tracked buckets (used by tests; harmless in production)."""
    with _windows._lock:
        _windows._buckets.clear()


def rate_limit(scope: str = "auth") -> Callable[[Request], None]:
    """FastAPI dependency: 429 when the client exceeds the configured limit."""

    def _check(request: Request) -> None:
        limit = _auth_limit_per_minute() if scope == "auth" else 0
        if limit <= 0:
            return
        allowed, retry_after = _windows.allow(scope, _client_ip(request), limit)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Retry in {int(retry_after)}s.",
                headers={"Retry-After": str(int(retry_after))},
            )

    return _check

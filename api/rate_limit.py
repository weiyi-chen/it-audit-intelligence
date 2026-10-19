"""Small in-memory rate limiter for the public demo endpoints.

This intentionally has no external dependency. It is suitable for the single
process public demo; a multi-instance production deployment should use Redis.
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


_LOCK = threading.Lock()
_REQUESTS: dict[str, deque[float]] = defaultdict(deque)


def demo_rate_limit() -> int:
    """Return the configured number of generation requests per hour and IP."""
    return max(1, int(os.getenv("DEMO_RATE_LIMIT_PER_HOUR", "5")))


def enforce_demo_rate_limit(request: Request) -> None:
    """Reject callers that exceed the public demo generation allowance."""
    forwarded = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded.split(",", 1)[0].strip()
    if not client_ip and request.client:
        client_ip = request.client.host
    key = client_ip or "unknown"
    now = time.monotonic()
    cutoff = now - 3600

    with _LOCK:
        timestamps = _REQUESTS[key]
        while timestamps and timestamps[0] <= cutoff:
            timestamps.popleft()
        limit = demo_rate_limit()
        if len(timestamps) >= limit:
            retry_after = max(1, int(3600 - (now - timestamps[0])))
            raise HTTPException(
                status_code=429,
                detail=f"Public demo limit reached ({limit} generations/hour). Try again later.",
                headers={"Retry-After": str(retry_after)},
            )
        timestamps.append(now)


def reset_rate_limits() -> None:
    """Clear counters (used by tests)."""
    with _LOCK:
        _REQUESTS.clear()

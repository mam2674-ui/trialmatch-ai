"""Simple in-process sliding-window rate limiter (per client IP).

Adequate for a single API instance. A multi-instance deployment should move this to Redis.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.core.config import get_settings

_hits: dict[str, deque[float]] = defaultdict(deque)


def rate_limit(request: Request) -> None:
    limit = get_settings().rate_limit_per_minute
    if limit <= 0:
        return
    key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window = _hits[key]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= limit:
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute and try again.")
    window.append(now)


def reset_rate_limits() -> None:
    _hits.clear()

"""
Rate limiting (tiêu chí 7) — Sliding window 60s lưu trong Redis.
"""
import time
import uuid
from collections import defaultdict, deque

from fastapi import HTTPException
from redis.exceptions import RedisError

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60
_fallback_windows: dict[str, deque[float]] = defaultdict(deque)


def _check_memory_fallback(key: str, limit: int, now: float) -> None:
    window = _fallback_windows[key]
    cutoff = now - WINDOW_SECONDS
    while window and window[0] < cutoff:
        window.popleft()
    if len(window) >= limit:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(WINDOW_SECONDS)},
        )
    window.append(now)


def check_rate_limit(key: str) -> None:
    """Giới hạn tối đa RATE_LIMIT_PER_MINUTE request/60s cho mỗi API key."""
    limit = settings.rate_limit_per_minute
    now = time.time()
    window_start = now - WINDOW_SECONDS

    if r is None:
        _check_memory_fallback(key, limit, now)
        return

    redis_key = f"rate_limit:{key}"
    try:
        pipe = r.pipeline()
        pipe.zremrangebyscore(redis_key, 0, window_start)
        pipe.zcard(redis_key)
        _, current_count = pipe.execute()

        if int(current_count) >= limit:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(WINDOW_SECONDS)},
            )

        member = f"{now}:{uuid.uuid4().hex}"
        pipe = r.pipeline()
        pipe.zadd(redis_key, {member: now})
        pipe.expire(redis_key, WINDOW_SECONDS + 5)
        pipe.execute()
    except HTTPException:
        raise
    except RedisError:
        _check_memory_fallback(key, limit, now)

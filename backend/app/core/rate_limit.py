"""Redis-backed rate limiting (transient state only)."""

from app.core.redis import get_redis


async def enforce_rate_limit(key: str, limit: int, window_seconds: int) -> None:
    """Raise RateLimitedError when `limit` is exceeded within the window."""
    if limit <= 0:
        return
    client = get_redis()
    window_key = f"ratelimit:{key}:{window_seconds}"
    try:
        count = await client.incr(window_key)
        if count == 1:
            await client.expire(window_key, window_seconds)
        elif count > limit:
            ttl = await client.ttl(window_key)
            raise RateLimited(ttl if ttl and ttl > 0 else window_seconds)
    except RateLimited:
        raise
    except Exception:
        # Redis unavailable: fail open rather than blocking all traffic.
        return


class RateLimited(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__("Rate limit exceeded")
        self.retry_after = retry_after

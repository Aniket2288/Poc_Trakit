import logging
import time

import redis
from fastapi import Request

from app.core.config import settings
from app.core.exceptions import RateLimitedError

logger = logging.getLogger("trackit.rate_limit")

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.redis_url, socket_timeout=0.5, socket_connect_timeout=0.5)
    return _client


def auth_rate_limit(request: Request) -> None:
    """
    Fixed-window limit: at most N requests per client IP per window on /auth/*.

    The key includes the window number (e.g. minute 29186543), so each window starts at zero and
    Redis deletes old keys by itself (EXPIRE). INCR is atomic, so two requests at once can't both read "9".
    Brute force on /auth/login gets 429 after N tries a minute.
    """
    limit, window = settings.auth_rate_limit, settings.auth_rate_window_seconds
    now = int(time.time())
    window_number = now // window
    ip = request.client.host if request.client else "unknown"
    key = f"ratelimit:auth:{ip}:{window_number}"

    try:
        pipe = get_redis().pipeline()
        pipe.incr(key)
        pipe.expire(key, window)
        count, _ = pipe.execute()
    except redis.RedisError:
        # Fail open: if Redis is down, let people log in rather than lock everyone out. Logged so we notice.
        logger.warning("rate limiter unavailable, allowing request")
        return

    if count > limit:
        retry_after = window - (now % window)
        raise RateLimitedError(f"Too many attempts. Try again in {retry_after} seconds", headers={"Retry-After": str(retry_after)})

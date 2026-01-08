# src/rlcoach/api/rate_limit.py
"""Rate limiting for API endpoints.

Uses Redis for distributed rate limiting in production,
with in-memory fallback for development.

SECURITY NOTE: Fail-Open Behavior
---------------------------------
The Redis rate limiter is configured to FAIL OPEN on errors.
This is an intentional availability vs security tradeoff:
- If Redis is down, requests are allowed through rather than blocking all users
- This prevents a Redis outage from causing a complete service denial
- For higher security requirements, change the fail-open behavior in
  RedisRateLimiter.check() to return allowed=False on exception

For production deployments with strict rate limiting requirements,
consider:
1. Running Redis in a high-availability configuration
2. Implementing a circuit breaker pattern
3. Falling back to in-memory limiting per-instance (less accurate but available)
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass
from functools import wraps
from typing import Callable

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

# Rate limit configurations (requests per window)
RATE_LIMITS = {
    "upload": {"requests": 10, "window_seconds": 60},  # 10 uploads per minute
    "chat": {"requests": 30, "window_seconds": 60},  # 30 messages per minute
    "notes": {"requests": 20, "window_seconds": 60},  # 20 notes per minute
    "benchmarks": {"requests": 30, "window_seconds": 60},  # 30 benchmark queries/min
    "gdpr": {"requests": 5, "window_seconds": 3600},  # 5 GDPR req/hour
    "default": {"requests": 100, "window_seconds": 60},  # 100 requests per minute
}


@dataclass
class RateLimitResult:
    """Result of rate limit check."""

    allowed: bool
    remaining: int
    reset_at: float
    limit: int


class InMemoryRateLimiter:
    """Simple in-memory rate limiter for development."""

    def __init__(self):
        # {user_id: {endpoint: [(timestamp, count)]}}
        self._requests: dict[str, dict[str, list[float]]] = defaultdict(
            lambda: defaultdict(list)
        )

    def check(
        self, user_id: str, endpoint: str, limit: int, window_seconds: int
    ) -> RateLimitResult:
        """Check if request is allowed under rate limit."""
        now = time.time()
        cutoff = now - window_seconds

        # Get recent requests within window
        user_requests = self._requests[user_id][endpoint]
        user_requests[:] = [ts for ts in user_requests if ts > cutoff]

        current_count = len(user_requests)
        remaining = max(0, limit - current_count - 1)
        reset_at = now + window_seconds

        if current_count >= limit:
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_at=reset_at,
                limit=limit,
            )

        # Record this request
        user_requests.append(now)

        return RateLimitResult(
            allowed=True,
            remaining=remaining,
            reset_at=reset_at,
            limit=limit,
        )


class RedisRateLimiter:
    """Redis-based distributed rate limiter for production."""

    def __init__(self, redis_client):
        self._redis = redis_client

    def check(
        self, user_id: str, endpoint: str, limit: int, window_seconds: int
    ) -> RateLimitResult:
        """Check if request is allowed under rate limit using sliding window."""
        now = time.time()
        key = f"ratelimit:{user_id}:{endpoint}"

        try:
            pipe = self._redis.pipeline()

            # Remove old entries outside window
            pipe.zremrangebyscore(key, 0, now - window_seconds)
            # Count requests in window
            pipe.zcard(key)
            # Add current request with score = timestamp
            pipe.zadd(key, {str(now): now})
            # Set TTL to clean up old keys
            pipe.expire(key, window_seconds + 1)

            results = pipe.execute()
            current_count = results[1]

            remaining = max(0, limit - current_count - 1)
            reset_at = now + window_seconds

            if current_count >= limit:
                # Remove the request we just added (it was rejected)
                self._redis.zrem(key, str(now))
                return RateLimitResult(
                    allowed=False,
                    remaining=0,
                    reset_at=reset_at,
                    limit=limit,
                )

            return RateLimitResult(
                allowed=True,
                remaining=remaining,
                reset_at=reset_at,
                limit=limit,
            )
        except Exception as e:
            logger.warning(f"Redis rate limit error, allowing request: {e}")
            # Fail open - allow request if Redis fails
            return RateLimitResult(
                allowed=True,
                remaining=limit,
                reset_at=now + window_seconds,
                limit=limit,
            )


# Global rate limiter instance
_rate_limiter: InMemoryRateLimiter | RedisRateLimiter | None = None


def get_rate_limiter() -> InMemoryRateLimiter | RedisRateLimiter:
    """Get or create the rate limiter instance."""
    global _rate_limiter

    if _rate_limiter is None:
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            try:
                import redis

                client = redis.from_url(redis_url)
                client.ping()  # Test connection
                _rate_limiter = RedisRateLimiter(client)
                logger.info("Using Redis rate limiter")
            except Exception as e:
                logger.warning(f"Redis unavailable, using in-memory rate limiter: {e}")
                _rate_limiter = InMemoryRateLimiter()
        else:
            _rate_limiter = InMemoryRateLimiter()
            logger.info("Using in-memory rate limiter (no REDIS_URL)")

    return _rate_limiter


def check_rate_limit(user_id: str, endpoint: str = "default") -> RateLimitResult:
    """Check rate limit for a user and endpoint.

    Args:
        user_id: The user's ID
        endpoint: The endpoint category (upload, chat, notes, default)

    Returns:
        RateLimitResult with allowed status and metadata
    """
    config = RATE_LIMITS.get(endpoint, RATE_LIMITS["default"])
    limiter = get_rate_limiter()
    return limiter.check(
        user_id=user_id,
        endpoint=endpoint,
        limit=config["requests"],
        window_seconds=config["window_seconds"],
    )


def rate_limit_response(result: RateLimitResult) -> HTTPException:
    """Create HTTP 429 response for rate limit exceeded."""
    retry_after = int(result.reset_at - time.time())
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
        headers={
            "Retry-After": str(retry_after),
            "X-RateLimit-Limit": str(result.limit),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(int(result.reset_at)),
        },
    )


def require_rate_limit(endpoint: str = "default"):
    """Decorator to apply rate limiting to an endpoint.

    Usage:
        @router.post("/upload")
        @require_rate_limit("upload")
        async def upload(user: AuthenticatedUser, ...):
            ...
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Find user in kwargs (from dependency injection)
            user = kwargs.get("user")
            if user and hasattr(user, "id"):
                result = check_rate_limit(user.id, endpoint)
                if not result.allowed:
                    raise rate_limit_response(result)
            return await func(*args, **kwargs)

        return wrapper

    return decorator

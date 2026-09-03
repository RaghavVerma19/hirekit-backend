"""
Rate Limiting Dependency for AI and High-Compute Endpoints.
Uses atomic Redis counters with graceful degradation and Retry-After headers.
"""
from typing import Callable
from fastapi import HTTPException, status, Depends
import redis.asyncio as aioredis
import structlog

from app.db.redis import get_redis
from app.models.user import User
from app.core.deps import get_current_user

logger = structlog.get_logger()


def rate_limit(
    max_requests: int = 10,
    window_seconds: int = 60,
    action: str = "ai_request",
) -> Callable:
    """
    FastAPI dependency factory enforcing per-user rate limits on expensive operations.
    """
    async def _limiter(
        current_user: User = Depends(get_current_user),
        redis: aioredis.Redis = Depends(get_redis),
    ) -> None:
        key = f"rate_limit:{action}:{current_user.id}"
        try:
            pipe = redis.pipeline()
            pipe.incr(key)
            pipe.ttl(key)
            results = await pipe.execute()

            count = results[0]
            ttl = results[1]

            if ttl == -1:
                await redis.expire(key, window_seconds)
                ttl = window_seconds

            if count > max_requests:
                retry_after = ttl if ttl > 0 else window_seconds
                logger.warning(
                    "rate_limit_exceeded",
                    user_id=current_user.id,
                    action=action,
                    count=count,
                    max=max_requests,
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded for {action.replace('_', ' ')}. Allowed: {max_requests} requests per {window_seconds}s. Please retry in {retry_after}s.",
                    headers={"Retry-After": str(retry_after)},
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("rate_limit_check_error", error=str(e))

    return _limiter

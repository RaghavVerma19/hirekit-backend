from typing import AsyncGenerator, Optional
import redis.asyncio as aioredis
from redis.asyncio import Redis
from app.core.config import settings

redis_client: Optional[Redis] = None


async def get_redis_client() -> Redis:
    """Get or create singleton Redis client pool."""
    global redis_client
    if redis_client is None:
        redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
        )
    return redis_client


async def close_redis() -> None:
    """Close Redis pool on shutdown."""
    global redis_client
    if redis_client is not None:
        await redis_client.close()
        redis_client = None


async def get_redis() -> AsyncGenerator[Redis, None]:
    """Dependency for yielding Redis client."""
    client = await get_redis_client()
    yield client

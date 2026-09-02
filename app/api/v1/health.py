from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.db.redis import get_redis
from app.db.session import get_db
from app.schemas.common import HealthOut

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthOut,
    status_code=status.HTTP_200_OK,
    summary="Liveness Probe",
)
async def health_check() -> HealthOut:
    """Basic liveness check."""
    return HealthOut(
        status="healthy",
        database="unknown",
        redis="unknown",
        version=__version__,
    )


@router.get(
    "/ready",
    response_model=HealthOut,
    status_code=status.HTTP_200_OK,
    summary="Readiness Probe",
)
async def readiness_check(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> JSONResponse:
    """Readiness probe checking PostgreSQL and Redis connection health."""
    db_status = "healthy"
    redis_status = "healthy"
    is_ready = True

    # 1. Check PostgreSQL
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_status = "unhealthy"
        is_ready = False

    # 2. Check Redis
    try:
        await redis.ping()
    except Exception:
        redis_status = "unhealthy"
        is_ready = False

    response_data = HealthOut(
        status="ready" if is_ready else "not_ready",
        database=db_status,
        redis=redis_status,
        version=__version__,
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=response_data.model_dump(),
    )

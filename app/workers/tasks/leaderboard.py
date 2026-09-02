from typing import Any, Dict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.session import AsyncSessionLocal
from app.models.resume import Resume
from app.services.leaderboard_service import LEADERBOARD_KEY

logger = structlog.get_logger()


async def recalculate_leaderboard_task(ctx: Dict[str, Any]) -> str:
    """Hourly background job: Reconcile DB highest ATS scores into Redis ZSET."""
    logger.info("recalculate_leaderboard_started")
    redis = ctx.get("redis")
    if not redis:
        logger.warning("redis_unavailable_for_leaderboard_task")
        return "skipped"

    async with AsyncSessionLocal() as db:
        # Find highest score for each student
        query = (
            select(Resume.user_id, func.max(Resume.ats_score).label("max_score"))
            .where(
                Resume.is_deleted.is_(False),
                Resume.leaderboard_eligible.is_(True),
                Resume.ats_score.isnot(None),
            )
            .group_by(Resume.user_id)
        )
        result = await db.execute(query)
        rows = result.all()

        if rows:
            zadd_mapping = {str(row.user_id): row.max_score for row in rows}
            # Replace / Update ZSET
            await redis.zadd(LEADERBOARD_KEY, zadd_mapping)
            logger.info("recalculate_leaderboard_completed", count=len(rows))
            return f"synced_{len(rows)}_scores"

    return "no_scores_to_sync"

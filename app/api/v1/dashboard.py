from typing import Any, Dict, List
from fastapi import APIRouter, Depends, status
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.redis import get_redis
from app.db.session import get_db
from app.models.user import User
from app.schemas.dashboard import (
    DashboardOverviewOut,
    LinkedInScoreOut,
    MyRankOut,
)
from app.schemas.user import UserOut
from app.services.leaderboard_service import LeaderboardService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get(
    "/overview",
    response_model=DashboardOverviewOut,
    status_code=status.HTTP_200_OK,
    summary="Get Aggregated Dashboard Overview",
)
async def get_dashboard_overview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> DashboardOverviewOut:
    """Aggregated dashboard payload with user profile, stats, top leaderboard, and LinkedIn metrics."""
    top_leaderboard = await LeaderboardService.get_top(redis, db, limit=3)

    linkedin_metrics = LinkedInScoreOut(
        profile_score=85,
        headline_score=90,
        experience_score=80,
        network_score=85,
        views=324,
        impressions=1420,
        appearances=89,
        updated_at="2 hours ago",
    )

    announcements: List[Dict[str, Any]] = [
        {
            "id": "ann-1",
            "title": "Google Placement Drive 2026 Registration Open",
            "body": "Google Software Engineering full-time and internship drive registrations are open till Friday.",
            "type": "placement",
            "tag": "Urgent",
            "created_at": "Today, 10:00 AM",
        },
        {
            "id": "ann-2",
            "title": "Resume Workshop by Senior TPO",
            "body": "Learn how to format resumes for ATS screeners and pass round 1 automated filters.",
            "type": "event",
            "tag": "Workshop",
            "created_at": "Yesterday",
        },
    ]

    return DashboardOverviewOut(
        user=UserOut.model_validate(current_user),
        active_jobs_count=12,
        applications_count=3,
        upcoming_interviews_count=1,
        leaderboard=top_leaderboard,
        linkedin=linkedin_metrics,
        announcements=announcements,
    )


@router.get(
    "/my-rank",
    response_model=MyRankOut,
    status_code=status.HTTP_200_OK,
    summary="Get My Rank & Percentile in Batch",
)
async def get_my_batch_rank(
    current_user: User = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
) -> MyRankOut:
    """Retrieve personal rank, percentile, and improvement tips from Redis ZSET."""
    return await LeaderboardService.get_my_rank(redis, current_user.id)

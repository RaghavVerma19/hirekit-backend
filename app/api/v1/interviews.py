from typing import List
from fastapi import APIRouter, Depends, status
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_role
from app.db.redis import get_redis
from app.db.session import get_db
from app.models.user import Role, User
from app.schemas.interview import InterviewCreate, InterviewOut
from app.services.interview_service import InterviewService

router = APIRouter(prefix="/interviews", tags=["Interviews"])


@router.get(
    "/upcoming",
    response_model=List[InterviewOut],
    status_code=status.HTTP_200_OK,
    summary="List My Upcoming Interviews",
)
async def list_upcoming_interviews(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[InterviewOut]:
    """Retrieve all upcoming scheduled interviews for the logged in candidate."""
    interviews = await InterviewService.list_upcoming(db, current_user.id)
    return [InterviewOut.model_validate(i) for i in interviews]


@router.post(
    "",
    response_model=InterviewOut,
    status_code=status.HTTP_201_CREATED,
    summary="Schedule Interview Round (TPO / Admin)",
)
async def schedule_interview(
    create_in: InterviewCreate,
    current_user: User = Depends(require_role([Role.ADMIN, Role.TPO])),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> InterviewOut:
    """Schedule a technical/HR interview round and push real-time alerts."""
    interview = await InterviewService.schedule_interview(db, redis, create_in)
    return InterviewOut.model_validate(interview)

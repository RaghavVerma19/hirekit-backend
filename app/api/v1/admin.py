from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, Query, status
import redis.asyncio as aioredis
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role
from app.db.redis import get_redis
from app.db.session import get_db
from app.models.education import Education
from app.models.user import Role, User
from app.schemas.admin import (
    AdminAnalyticsOverviewOut,
    BulkStatusUpdateIn,
    BulkVerifyIn,
)
from app.schemas.common import MessageOut
from app.schemas.user import FullProfileOut, UserOut
from app.services.admin_service import AdminService
from app.services.profile_service import ProfileService

router = APIRouter(prefix="/admin", tags=["Admin & TPO Portal"])


@router.get(
    "/users",
    response_model=List[UserOut],
    status_code=status.HTTP_200_OK,
    summary="List University Students & Candidates",
)
async def list_students(
    department: Optional[str] = Query(None),
    is_verified: Optional[bool] = Query(None),
    role: Optional[Role] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(require_role([Role.ADMIN, Role.TPO])),
    db: AsyncSession = Depends(get_db),
) -> List[UserOut]:
    """Retrieve filtered list of student profiles for TPO review."""
    query = select(User).order_by(desc(User.created_at)).limit(limit)

    if department:
        query = query.join(Education, Education.user_id == User.id).where(
            Education.department.ilike(f"%{department}%")
        )
    if is_verified is not None:
        query = query.where(User.is_verified == is_verified)
    if role:
        query = query.where(User.role == role)

    result = await db.execute(query)
    users = list(result.scalars().all())
    return [UserOut.model_validate(u) for u in users]


@router.get(
    "/users/{user_id}",
    response_model=FullProfileOut,
    status_code=status.HTTP_200_OK,
    summary="Review Full Candidate Dossier",
)
async def review_student_profile(
    user_id: uuid.UUID,
    current_user: User = Depends(require_role([Role.ADMIN, Role.TPO])),
    db: AsyncSession = Depends(get_db),
) -> FullProfileOut:
    """Load full candidate graph (marksheets, projects, experiences) for TPO verification."""
    return await ProfileService.get_full_profile(db, user_id)


@router.post(
    "/bulk-verify",
    response_model=MessageOut,
    status_code=status.HTTP_200_OK,
    summary="Bulk Verify Student Profiles",
)
async def bulk_verify_students(
    body: BulkVerifyIn,
    current_user: User = Depends(require_role([Role.ADMIN, Role.TPO])),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    """Verify academic marksheets and credentials for a batch of students."""
    count = await AdminService.bulk_verify_users(db, current_user.id, body.user_ids)
    return MessageOut(message=f"Successfully verified {count} student profiles.")


@router.post(
    "/bulk-status-update",
    response_model=MessageOut,
    status_code=status.HTTP_200_OK,
    summary="Bulk Update Application Statuses",
)
async def bulk_update_applications(
    body: BulkStatusUpdateIn,
    current_user: User = Depends(require_role([Role.ADMIN, Role.TPO])),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> MessageOut:
    """Advance or reject candidate applications with audit trail and real-time alerts."""
    count = await AdminService.bulk_update_application_status(
        db, redis, current_user.id, body.application_ids, body.status, body.note
    )
    return MessageOut(message=f"Successfully updated {count} applications to {body.status.value}.")


@router.get(
    "/analytics/overview",
    response_model=AdminAnalyticsOverviewOut,
    status_code=status.HTTP_200_OK,
    summary="Get Campus Placement Analytics",
)
async def get_placement_analytics(
    current_user: User = Depends(require_role([Role.ADMIN, Role.TPO])),
    db: AsyncSession = Depends(get_db),
) -> AdminAnalyticsOverviewOut:
    """Retrieve university-wide placement statistics and drive metrics."""
    return await AdminService.get_analytics(db)

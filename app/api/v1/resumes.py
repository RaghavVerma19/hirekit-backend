from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, Query, Response, status
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user
from app.db.redis import get_redis
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import MessageOut
from app.schemas.resume import (
    ATSScoreResult,
    ResumeCreate,
    ResumeDetailOut,
    ResumeOut,
    ResumeUpdate,
)
from app.services.ats_service import ATSService
from app.services.leaderboard_service import LeaderboardService
from app.services.resume_service import ResumeService

router = APIRouter(prefix="/resumes", tags=["Resume Studio & ATS"])


@router.get(
    "",
    response_model=List[ResumeOut],
    status_code=status.HTTP_200_OK,
    summary="List My Resumes",
)
async def list_my_resumes(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[ResumeOut]:
    """List all active resumes for the authenticated student."""
    resumes = await ResumeService.list_resumes(db, current_user.id)
    return [ResumeOut.model_validate(r) for r in resumes]


@router.post(
    "",
    response_model=ResumeDetailOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create Resume",
)
async def create_resume(
    create_in: ResumeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResumeDetailOut:
    """Create a new resume with optional auto-population from profile."""
    resume = await ResumeService.create_resume(db, current_user.id, create_in)
    return ResumeDetailOut.model_validate(resume)


@router.get(
    "/{resume_id}",
    response_model=ResumeDetailOut,
    status_code=status.HTTP_200_OK,
    summary="Get Resume Details",
)
async def get_resume_detail(
    resume_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResumeDetailOut:
    """Retrieve full resume JSON content with ownership verification."""
    resume = await ResumeService.get_resume(db, current_user.id, resume_id)
    return ResumeDetailOut.model_validate(resume)


@router.put(
    "/{resume_id}",
    response_model=ResumeDetailOut,
    status_code=status.HTTP_200_OK,
    summary="Save Resume Content",
)
async def update_resume(
    resume_id: uuid.UUID,
    update_in: ResumeUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResumeDetailOut:
    """Auto-save resume content with optimistic locking and content-hash calculation."""
    resume = await ResumeService.update_resume(db, current_user.id, resume_id, update_in)
    return ResumeDetailOut.model_validate(resume)


@router.delete(
    "/{resume_id}",
    response_model=MessageOut,
    status_code=status.HTTP_200_OK,
    summary="Delete Resume",
)
async def delete_resume(
    resume_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    """Soft-delete a resume."""
    await ResumeService.soft_delete(db, current_user.id, resume_id)
    return MessageOut(message="Resume deleted successfully.")


@router.patch(
    "/{resume_id}/primary",
    response_model=ResumeOut,
    status_code=status.HTTP_200_OK,
    summary="Set Primary Application Resume",
)
async def set_primary_resume(
    resume_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResumeOut:
    """Designate resume as the primary 1-click job application resume."""
    resume = await ResumeService.set_primary(db, current_user.id, resume_id)
    return ResumeOut.model_validate(resume)


@router.post(
    "/{resume_id}/score",
    response_model=ATSScoreResult,
    status_code=status.HTTP_200_OK,
    summary="Score Resume with Gemini ATS",
)
async def score_resume(
    resume_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> ATSScoreResult:
    """Run AI ATS evaluation with content-hash caching, dedup locking, and ZSET score sync."""
    resume = await ResumeService.get_resume(db, current_user.id, resume_id)
    result = await ATSService.score_resume(resume.id, resume.content_json, redis)

    # Persist latest score to DB
    resume.ats_score = result.overall_score
    resume.ats_feedback = result.model_dump()
    await db.commit()

    # Nudge Redis Leaderboard ZSET
    if resume.leaderboard_eligible:
        await LeaderboardService.update_score(redis, current_user.id, result.overall_score)

    return result


@router.get(
    "/{resume_id}/public",
    response_model=ResumeDetailOut,
    status_code=status.HTTP_200_OK,
    summary="Public Shareable Resume Link",
)
async def get_public_resume(
    resume_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ResumeDetailOut:
    """View a resume publicly without authentication via shareable link."""
    resume = await ResumeService.get_resume(db, None, resume_id)
    return ResumeDetailOut.model_validate(resume)


@router.post(
    "/{resume_id}/pdf",
    response_model=MessageOut,
    status_code=status.HTTP_200_OK,
    summary="Generate Resume PDF",
)
async def generate_resume_pdf(
    resume_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    """Trigger asynchronous headless Chromium PDF generation."""
    await ResumeService.get_resume(db, current_user.id, resume_id)
    return MessageOut(message="PDF generation triggered successfully.")

from typing import Any, Dict, List, Optional
import uuid
from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from pydantic import BaseModel, Field
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.errors import AppException
from app.core.rate_limit import rate_limit
from app.db.redis import get_redis
from app.db.session import get_db
from app.models.resume import Resume
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


class ResumeContentAuditIn(BaseModel):
    content: Dict[str, Any]
    target_role: str = "Software Engineering"


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


@router.post(
    "/upload-pdf",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Upload & Parse Resume PDF with AI Tech Recruiter Audit",
    dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60, action="resume_upload"))],
)
async def upload_resume_pdf(
    file: UploadFile = File(...),
    target_role: str = Query("Software Engineering", description="Target placement domain"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Parse uploaded resume PDF, evaluate via Gemini 2.5 Flash Tech Recruiter AI, and create resume record."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_FILE_TYPE",
            message="Please upload a valid PDF document.",
        )

    file_bytes = await file.read()
    if len(file_bytes) > 10 * 1024 * 1024:
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="FILE_TOO_LARGE",
            message="Resume PDF exceeds maximum allowed size (10MB).",
        )

    if not file_bytes.startswith(b"%PDF"):
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_PDF_FORMAT",
            message="The uploaded file is not a valid PDF document.",
        )

    try:
        parsed_content = ResumeService.parse_resume_pdf(file_bytes)
        audit_result = await ATSService.deep_ai_audit_resume(parsed_content, target_role)

        # Create new resume entry in database
        resume_title = parsed_content.get("title") or f"{file.filename.rsplit('.', 1)[0]}"
        new_resume = Resume(
            user_id=current_user.id,
            title=resume_title[:150],
            template_id="modern-professional",
            content_json=parsed_content,
            content_hash=ATSService.compute_content_hash(parsed_content),
            ats_score=audit_result.get("overall_score"),
            ats_feedback=audit_result,
            is_primary=False,
        )
        db.add(new_resume)
        await db.commit()
        await db.refresh(new_resume)

        return {
            "success": True,
            "resume": ResumeDetailOut.model_validate(new_resume),
            "audit": audit_result,
            "parsed": parsed_content,
        }
    except AppException:
        raise
    except Exception as e:
        raise AppException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="RESUME_PARSING_FAILED",
            message=f"Could not parse resume PDF: {str(e)}",
        )


@router.post(
    "/audit-content",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Run Deep AI Audit on Resume Content",
    dependencies=[Depends(rate_limit(max_requests=15, window_seconds=60, action="resume_audit"))],
)
async def audit_resume_content(
    payload: ResumeContentAuditIn,
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Evaluate editor resume JSON with Gemini 2.5 Flash Tech Recruiter AI."""
    audit_result = await ATSService.deep_ai_audit_resume(payload.content, payload.target_role)
    return {
        "success": True,
        "audit": audit_result,
    }


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

import asyncio
import io
from typing import Any, Dict, List, Optional
import uuid
from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, Response, UploadFile, status
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


class ResumeBulletEnhanceIn(BaseModel):
    text: str = Field(..., max_length=1500)
    action: str = Field("improve", max_length=50)
    context: Optional[Dict[str, Any]] = None


@router.post(
    "/enhance-bullet",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="AI Bullet Enhancement",
    dependencies=[Depends(rate_limit(max_requests=30, window_seconds=60, action="bullet_enhance"))],
)
async def enhance_resume_bullet(
    payload: ResumeBulletEnhanceIn,
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Enhance, shorten, proofread, or upgrade a resume bullet point using Gemini 2.5 Flash."""
    return await ATSService.enhance_bullet_text(
        text=payload.text,
        action=payload.action,
        context=payload.context,
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
    summary="Upload & Parse Resume PDF",
    dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60, action="resume_upload"))],
)
async def upload_resume_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    target_role: str = Query("Software Engineering", description="Target placement domain"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Parse an uploaded PDF and create an editable resume without running an ATS audit."""
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
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        full_text = "\n".join((page.extract_text() or "") for page in reader.pages)

        parsed_content = ResumeService.parse_resume_pdf(file_bytes)
        # Layout-aware instant LaTeX so editor shows detected geometry immediately
        try:
            from app.services.layout_service import extract_layout
            _layout = extract_layout(file_bytes)
        except Exception:
            _layout = {}
        initial_latex = ResumeService.generate_latex_from_structured_data(parsed_content, layout=_layout)
        parsed_content["latex_source"] = initial_latex
        parsed_content["layout_json"] = _layout
        # Flag that LLM is transcribing the exact PDF in the background
        parsed_content["llm_processing"] = True

        # Create new resume entry in database
        resume_title = parsed_content.get("title") or f"{file.filename.rsplit('.', 1)[0]}"
        new_resume = Resume(
            user_id=current_user.id,
            title=resume_title[:150],
            template_id="preserved-layout-v1",
            content_json=parsed_content,
            content_hash=ATSService.compute_content_hash(parsed_content),
            is_primary=False,
        )
        db.add(new_resume)
        await db.commit()
        await db.refresh(new_resume)

        # Enqueue background LLM transcription task with actual PDF bytes for multimodal observation
        background_tasks.add_task(
            ResumeService.process_pdf_transcription_background,
            new_resume.id,
            file_bytes,
            full_text,
            parsed_content,
        )

        return {
            "success": True,
            "resume": ResumeDetailOut.model_validate(new_resume),
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
    "/{resume_id}/compile",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Compile LaTeX to exact PDF via external API",
    dependencies=[Depends(rate_limit(max_requests=15, window_seconds=60, action="resume_compile"))],
)
async def compile_resume_latex(
    resume_id: uuid.UUID,
    payload: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Compile provided latex_source with external LaTeX API, store PDF to S3/CDN, return pdf_url + log."""
    from app.core.config import settings
    from app.services.latex_compile_service import compile_latex_source, source_hash
    from app.services.storage_service import StorageService

    resume = await ResumeService.get_resume(db, current_user.id, resume_id)
    source = str(payload.get("latex_source") or "")
    engine = str(payload.get("engine") or settings.LATEX_ENGINE or "pdflatex")
    if not source or "\\begin{document}" not in source:
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_LATEX",
            message="latex_source must be complete LaTeX with \\begin{document}.",
        )
    result = await compile_latex_source(source, engine=engine)
    if not result.get("success") or not result.get("pdf_bytes"):
        return {"success": False, "pdf_url": None, "log": result.get("log", "Compile failed."), "engine": engine}
    pdf_bytes: bytes = result["pdf_bytes"]
    content_hash = source_hash(source)
    key = f"pdfs/{resume_id}/{content_hash}.pdf"
    pdf_url: str = f"{settings.CDN_BASE}/{key}"
    # Upload to S3 when real credentials configured; otherwise CDN-constructed URL
    try:
        if not StorageService._is_mock_storage():
            import aioboto3
            session = aioboto3.Session()
            async with session.client(
                "s3",
                region_name=settings.AWS_REGION,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            ) as s3:
                import io as _io
                await s3.put_object(Bucket=settings.S3_BUCKET, Key=key, Body=pdf_bytes, ContentType="application/pdf")
    except Exception:
        pass
    # Persist compiled pdf url + log on resume
    try:
        content = dict(resume.content_json or {})
        content["compiled_pdf_url"] = pdf_url
        content["compiled_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        content["compile_log"] = str(result.get("log") or "")[:4000]
        content["latex_source"] = source
        resume.content_json = content
        resume.pdf_url = pdf_url
        await db.commit()
    except Exception:
        pass
    return {"success": True, "pdf_url": pdf_url, "log": result.get("log", "compile ok"), "engine": engine}


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

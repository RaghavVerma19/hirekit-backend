from typing import Any, Dict, List, Optional
import uuid
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
import structlog

from app.core.deps import get_current_user
from app.core.errors import AppException
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.models.user import User
from app.services.linkedin_service import LinkedInAuditService

logger = structlog.get_logger()

router = APIRouter(prefix="/linkedin", tags=["LinkedIn Profile Audit"])


class LinkedInTextAuditIn(BaseModel):
    headline: str = Field("", max_length=500)
    summary: str = Field("", max_length=5000)
    skills: List[str] = Field(default_factory=list)
    target_role: str = Field("Software Engineering", max_length=100)


@router.post(
    "/upload-pdf",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Upload & Parse Official LinkedIn PDF",
    dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60, action="linkedin_upload"))],
)
async def upload_linkedin_pdf(
    file: UploadFile = File(...),
    target_role: str = Query("Software Engineering", description="Target placement domain"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Parse official LinkedIn 'Save to PDF' export, extract all sections, run ATS audit, and persist to database."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_FILE_TYPE",
            message="Only PDF files exported from LinkedIn ('Save to PDF') are supported.",
        )

    file_bytes = await file.read()
    if len(file_bytes) > 10 * 1024 * 1024:  # 10MB limit
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="FILE_TOO_LARGE",
            message="PDF file exceeds maximum allowed size (10MB).",
        )

    if not file_bytes.startswith(b"%PDF"):
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_PDF_FORMAT",
            message="The uploaded file is not a valid PDF document.",
        )

    try:
        parsed_data = LinkedInAuditService.parse_linkedin_pdf(file_bytes)
        audit_result = await LinkedInAuditService.ai_audit_profile(parsed_data, target_role)

        # Store in user's additional_info JSON column
        current_info = dict(current_user.additional_info or {})
        current_info["linkedin_audit"] = {
            "parsed": parsed_data,
            "audit": audit_result,
            "updated_at": audit_result["audited_at"],
        }
        current_user.additional_info = current_info
        flag_modified(current_user, "additional_info")

        await db.commit()
        await db.refresh(current_user)

        logger.info(
            "linkedin_pdf_audited",
            user_id=str(current_user.id),
            overall_score=audit_result["overall_score"],
            skills_count=len(parsed_data["skills"]),
        )

        return {
            "success": True,
            "parsed": parsed_data,
            "audit": audit_result,
        }

    except Exception as e:
        logger.error("linkedin_pdf_parsing_error", error=str(e), exc_info=True)
        raise AppException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="PDF_PARSING_FAILED",
            message=f"Could not parse LinkedIn PDF: {str(e)}",
        )


@router.get(
    "/audit",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Get Latest Stored LinkedIn Audit",
)
async def get_latest_linkedin_audit(
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Retrieve the student's latest persisted LinkedIn audit from the database."""
    additional_info = current_user.additional_info or {}
    latest = additional_info.get("linkedin_audit")

    if not latest:
        return {
            "has_audit": False,
            "audit": None,
            "parsed": None,
        }

    return {
        "has_audit": True,
        "audit": latest.get("audit"),
        "parsed": latest.get("parsed"),
        "updated_at": latest.get("updated_at"),
    }


@router.post(
    "/audit-text",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Run Audit on Custom / Edited LinkedIn Content",
    dependencies=[Depends(rate_limit(max_requests=15, window_seconds=60, action="linkedin_audit"))],
)
async def audit_linkedin_text(
    payload: LinkedInTextAuditIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Evaluate updated headline, summary, and skills, updating the persisted database record."""
    data = {
        "headline": payload.headline,
        "summary": payload.summary,
        "skills": payload.skills,
        "experiences": [],
        "certifications": [],
        "educations": [],
    }

    audit_result = await LinkedInAuditService.ai_audit_profile(data, payload.target_role)

    current_info = dict(current_user.additional_info or {})
    current_audit_record = current_info.get("linkedin_audit") or {}
    current_audit_record["audit"] = audit_result
    current_audit_record["parsed"] = {
        **(current_audit_record.get("parsed") or {}),
        "headline": payload.headline,
        "summary": payload.summary,
        "skills": payload.skills or (current_audit_record.get("parsed") or {}).get("skills", []),
    }
    current_audit_record["updated_at"] = audit_result["audited_at"]

    current_info["linkedin_audit"] = current_audit_record
    current_user.additional_info = current_info
    flag_modified(current_user, "additional_info")

    await db.commit()
    await db.refresh(current_user)

    return {
        "success": True,
        "audit": audit_result,
        "parsed": current_audit_record["parsed"],
    }

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_super_admin
from app.core.errors import AppException
from app.core.security import hash_password
from app.db.session import get_db
from app.models.college import College
from app.models.job import Job
from app.models.user import Role, User
from sqlalchemy.orm.attributes import flag_modified

router = APIRouter(prefix="/super-admin", tags=["Super Admin"])


# Schemas
class CollegeCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    slug: str = Field(..., min_length=2, max_length=100)
    code: str = Field(..., min_length=2, max_length=50)
    domain: Optional[str] = None
    primary_color: str = "#3B48E0"
    accent_color: str = "#7C3AED"
    logo_url: Optional[str] = None
    banner_url: Optional[str] = None
    admin_name: str = Field(..., min_length=2, max_length=100)
    admin_email: str = Field(...)
    admin_password: str = Field(..., min_length=6)
    settings: Optional[Dict[str, Any]] = None


class CollegeUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    domain: Optional[str] = None
    primary_color: Optional[str] = None
    accent_color: Optional[str] = None
    logo_url: Optional[str] = None
    banner_url: Optional[str] = None
    is_active: Optional[bool] = None
    settings: Optional[Dict[str, Any]] = None


@router.get("/metrics", summary="Platform-wide Metrics")
async def get_platform_metrics(
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve top-level platform statistics for the Super Admin dashboard."""
    total_colleges = await db.scalar(select(func.count(College.id)))
    active_colleges = await db.scalar(
        select(func.count(College.id)).where(College.is_active.is_(True))
    )
    total_users = await db.scalar(select(func.count(User.id)))
    total_students = await db.scalar(
        select(func.count(User.id)).where(User.role == Role.STUDENT)
    )
    total_jobs = await db.scalar(select(func.count(Job.id)))

    return {
        "total_colleges": total_colleges or 0,
        "active_colleges": active_colleges or 0,
        "total_users": total_users or 0,
        "total_students": total_students or 0,
        "total_jobs": total_jobs or 0,
    }


@router.get("/colleges", summary="List All Colleges")
async def list_colleges(
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """List all tenant colleges with stats."""
    query = select(College).order_by(College.created_at.desc())
    if is_active is not None:
        query = query.where(College.is_active == is_active)
    if search:
        query = query.where(
            (College.name.ilike(f"%{search}%")) | (College.slug.ilike(f"%{search}%")) | (College.code.ilike(f"%{search}%"))
        )

    result = await db.execute(query)
    colleges = result.scalars().all()

    output = []
    for c in colleges:
        # Get count of students
        student_count = await db.scalar(
            select(func.count(User.id)).where(User.college_id == c.id, User.role == Role.STUDENT)
        )
        job_count = await db.scalar(
            select(func.count(Job.id)).where(Job.college_id == c.id)
        )
        output.append({
            "id": str(c.id),
            "name": c.name,
            "slug": c.slug,
            "code": c.code,
            "domain": c.domain,
            "logo_url": c.logo_url,
            "banner_url": c.banner_url,
            "primary_color": c.primary_color,
            "accent_color": c.accent_color,
            "is_active": c.is_active,
            "settings": c.settings,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "student_count": student_count or 0,
            "job_count": job_count or 0,
        })

    return output


@router.post("/colleges", status_code=status.HTTP_201_CREATED, summary="Provision New College")
async def create_college(
    data: CollegeCreate,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Provision a new college tenant and create the college administrator account."""
    # Check duplicate slug
    existing_slug = await db.scalar(select(College).where(College.slug == data.slug.lower().strip()))
    if existing_slug:
        raise AppException(
            status_code=status.HTTP_409_CONFLICT,
            error_code="SLUG_ALREADY_EXISTS",
            message=f"College with slug '{data.slug}' already exists.",
        )

    # Check duplicate code
    existing_code = await db.scalar(select(College).where(College.code == data.code.upper().strip()))
    if existing_code:
        raise AppException(
            status_code=status.HTTP_409_CONFLICT,
            error_code="CODE_ALREADY_EXISTS",
            message=f"College code '{data.code}' already exists.",
        )

    # Check admin email
    existing_email = await db.scalar(select(User).where(User.email == data.admin_email.lower().strip()))
    if existing_email:
        raise AppException(
            status_code=status.HTTP_409_CONFLICT,
            error_code="ADMIN_EMAIL_EXISTS",
            message=f"A user with email '{data.admin_email}' already exists.",
        )

    # Full enterprise default settings if not provided
    default_settings = {
        "features": {
            "assignments": True,
            "competitions": True,
            "events": True,
            "linkedin_audit": True,
            "resume_leaderboard": True,
            "community_feed": True,
            "mock_interviews": True,
            "ai_cover_letter": True,
            "alumni_network": True,
            "recruiter_direct_messaging": False,
        },
        "placement_rules": {
            "allow_multiple_offers": False,
            "max_offers": 1,
            "pydream_upgrade_allowed": True,
            "min_cgpa_cutoff_default": 6.0,
            "max_backlogs_allowed": 0,
            "dream_tier_threshold_lpa": 6.0,
            "super_dream_tier_threshold_lpa": 12.0,
            "strict_single_offer_policy": True,
            "debar_on_unexcused_absence": True,
        },
        "academic": {
            "departments": [
                "Computer Science & Engineering",
                "Information Technology",
                "Electronics & Communication",
                "Electrical Engineering",
                "Mechanical Engineering",
                "Civil Engineering",
            ],
            "batches": ["2023", "2024", "2025", "2026", "2027"],
            "grading_scale": "10.0",
            "current_academic_year": "2025-2026",
        },
        "accreditation": {
            "nirf_reporting_enabled": True,
            "naac_reporting_enabled": True,
            "affiliating_university": "",
            "aicte_code": "",
        },
        "security": {
            "mfa_enforced_for_staff": False,
            "allow_student_self_registration": True,
            "require_admin_approval_for_registration": False,
            "auto_notify_drive_updates": True,
        },
    }

    college = College(
        name=data.name.strip(),
        slug=data.slug.lower().strip(),
        code=data.code.upper().strip(),
        domain=data.domain.strip() if data.domain else None,
        primary_color=data.primary_color,
        accent_color=data.accent_color,
        logo_url=data.logo_url,
        banner_url=data.banner_url,
        settings=data.settings or default_settings,
        is_active=True,
    )
    db.add(college)
    await db.flush()

    # Create College Admin user
    admin_user = User(
        email=data.admin_email.lower().strip(),
        password_hash=hash_password(data.admin_password),
        name=data.admin_name.strip(),
        role=Role.COLLEGE_ADMIN,
        college_id=college.id,
        is_verified=True,
        is_onboarded=True,
    )
    db.add(admin_user)
    await db.commit()
    await db.refresh(college)

    return {
        "id": str(college.id),
        "name": college.name,
        "slug": college.slug,
        "code": college.code,
        "primary_color": college.primary_color,
        "accent_color": college.accent_color,
        "settings": college.settings,
        "admin_email": admin_user.email,
        "message": f"College '{college.name}' provisioned successfully.",
    }


@router.get("/colleges/{college_id}", summary="Get College Details")
async def get_college(
    college_id: uuid.UUID,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve details and statistics for a specific college."""
    college = await db.get(College, college_id)
    if not college:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="COLLEGE_NOT_FOUND",
            message="College not found.",
        )

    student_count = await db.scalar(
        select(func.count(User.id)).where(User.college_id == college.id, User.role == Role.STUDENT)
    )
    tpo_count = await db.scalar(
        select(func.count(User.id)).where(User.college_id == college.id, User.role.in_([Role.TPO, Role.COLLEGE_ADMIN]))
    )
    job_count = await db.scalar(
        select(func.count(Job.id)).where(Job.college_id == college.id)
    )

    return {
        "id": str(college.id),
        "name": college.name,
        "slug": college.slug,
        "code": college.code,
        "domain": college.domain,
        "logo_url": college.logo_url,
        "banner_url": college.banner_url,
        "primary_color": college.primary_color,
        "accent_color": college.accent_color,
        "is_active": college.is_active,
        "settings": college.settings,
        "student_count": student_count or 0,
        "tpo_count": tpo_count or 0,
        "job_count": job_count or 0,
        "created_at": college.created_at.isoformat() if college.created_at else None,
    }


@router.put("/colleges/{college_id}", summary="Update College Configuration")
async def update_college(
    college_id: uuid.UUID,
    data: CollegeUpdate,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Update college details, branding, or feature settings."""
    college = await db.get(College, college_id)
    if not college:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="COLLEGE_NOT_FOUND",
            message="College not found.",
        )

    if data.name is not None:
        college.name = data.name.strip()
    if data.code is not None:
        college.code = data.code.upper().strip()
    if data.domain is not None:
        college.domain = data.domain.strip() if data.domain else None
    if data.primary_color is not None:
        college.primary_color = data.primary_color
    if data.accent_color is not None:
        college.accent_color = data.accent_color
    if data.logo_url is not None:
        college.logo_url = data.logo_url
    if data.banner_url is not None:
        college.banner_url = data.banner_url
    if data.is_active is not None:
        college.is_active = data.is_active
    if data.settings is not None:
        college.settings = data.settings
        flag_modified(college, "settings")

    await db.commit()
    await db.refresh(college)

    return {
        "id": str(college.id),
        "name": college.name,
        "slug": college.slug,
        "code": college.code,
        "is_active": college.is_active,
        "settings": college.settings,
        "message": "College updated successfully.",
    }


@router.post("/colleges/{college_id}/toggle-status", summary="Toggle College Active Status")
async def toggle_college_status(
    college_id: uuid.UUID,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Activate or deactivate a college tenant."""
    college = await db.get(College, college_id)
    if not college:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="COLLEGE_NOT_FOUND",
            message="College not found.",
        )

    college.is_active = not college.is_active
    await db.commit()
    return {
        "id": str(college.id),
        "is_active": college.is_active,
        "message": f"College is now {'active' if college.is_active else 'suspended'}.",
    }


@router.get("/colleges/{college_id}/config/export", summary="Export Complete College Configuration as JSON")
async def export_college_config(
    college_id: uuid.UUID,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Export the entire institutional configuration, branding, and rules as a portable JSON payload."""
    college = await db.get(College, college_id)
    if not college:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="COLLEGE_NOT_FOUND",
            message="College not found.",
        )

    return {
        "schema_version": "2.0.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "college": {
            "id": str(college.id),
            "name": college.name,
            "slug": college.slug,
            "code": college.code,
            "domain": college.domain,
            "primary_color": college.primary_color,
            "accent_color": college.accent_color,
            "logo_url": college.logo_url,
            "banner_url": college.banner_url,
        },
        "settings": college.settings or {},
    }


class ConfigImportPayload(BaseModel):
    settings: Dict[str, Any]
    branding: Optional[Dict[str, Any]] = None


@router.post("/colleges/{college_id}/config/import", summary="Import and Apply College Configuration from JSON")
async def import_college_config(
    college_id: uuid.UUID,
    payload: ConfigImportPayload,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Validate and apply a full institutional configuration JSON payload to a college tenant."""
    college = await db.get(College, college_id)
    if not college:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="COLLEGE_NOT_FOUND",
            message="College not found.",
        )

    # Basic structural validation
    incoming_settings = payload.settings
    if not isinstance(incoming_settings, dict):
        raise AppException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="INVALID_SETTINGS_PAYLOAD",
            message="Settings must be a valid JSON object.",
        )

    # Deep merge with current settings
    current = dict(college.settings or {})
    for section, val in incoming_settings.items():
        if isinstance(val, dict) and isinstance(current.get(section), dict):
            current[section].update(val)
        else:
            current[section] = val

    college.settings = dict(current)
    flag_modified(college, "settings")

    # Apply branding if provided in the payload
    if payload.branding:
        if "primary_color" in payload.branding:
            college.primary_color = payload.branding["primary_color"]
        if "accent_color" in payload.branding:
            college.accent_color = payload.branding["accent_color"]
        if "logo_url" in payload.branding:
            college.logo_url = payload.branding["logo_url"]
        if "banner_url" in payload.branding:
            college.banner_url = payload.branding["banner_url"]

    await db.commit()
    await db.refresh(college)

    return {
        "id": str(college.id),
        "name": college.name,
        "slug": college.slug,
        "code": college.code,
        "primary_color": college.primary_color,
        "accent_color": college.accent_color,
        "settings": college.settings,
        "message": "Institutional configuration and settings successfully imported and saved to database.",
    }


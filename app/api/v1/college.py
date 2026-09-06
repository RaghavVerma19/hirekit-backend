from typing import Any, Dict, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_college_admin
from app.core.errors import AppException
from app.db.session import get_db
from app.models.college import College
from app.models.user import User

router = APIRouter(prefix="/college", tags=["College"])


class CollegeSettingsUpdate(BaseModel):
    name: Optional[str] = None
    primary_color: Optional[str] = None
    accent_color: Optional[str] = None
    logo_url: Optional[str] = None
    banner_url: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None


@router.get("/by-slug/{slug}", summary="Get Public College Branding by Slug")
async def get_college_by_slug(
    slug: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve public branding and enabled feature flags for a college by its URL slug."""
    college = await db.scalar(
        select(College).where(College.slug == slug.lower().strip(), College.is_active.is_(True))
    )
    if not college:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="COLLEGE_NOT_FOUND",
            message=f"No active college found for slug '{slug}'.",
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
        "settings": college.settings,
    }


@router.get("/current", summary="Get Authenticated User's College Settings")
async def get_current_college(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve full college profile and configuration for the logged-in user."""
    if not current_user.college_id:
        # Fallback to default college or return empty for super admin
        default_college = await db.get(College, uuid.UUID("00000000-0000-0000-0000-000000000001"))
        if default_college:
            return {
                "id": str(default_college.id),
                "name": default_college.name,
                "slug": default_college.slug,
                "code": default_college.code,
                "domain": default_college.domain,
                "logo_url": default_college.logo_url,
                "banner_url": default_college.banner_url,
                "primary_color": default_college.primary_color,
                "accent_color": default_college.accent_color,
                "settings": default_college.settings,
            }
        return {"message": "User has no tenant assigned"}

    college = await db.get(College, current_user.college_id)
    if not college:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="COLLEGE_NOT_FOUND",
            message="Associated college not found.",
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
        "settings": college.settings,
    }


@router.put("/settings", summary="Update College Institutional Settings")
async def update_current_college_settings(
    data: CollegeSettingsUpdate,
    current_user: User = Depends(require_college_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Update current college's branding, feature flags, or placement policies."""
    college_id = current_user.college_id or uuid.UUID("00000000-0000-0000-0000-000000000001")
    college = await db.get(College, college_id)
    if not college:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="COLLEGE_NOT_FOUND",
            message="College not found.",
        )

    if data.name is not None:
        college.name = data.name.strip()
    if data.primary_color is not None:
        college.primary_color = data.primary_color
    if data.accent_color is not None:
        college.accent_color = data.accent_color
    if data.logo_url is not None:
        college.logo_url = data.logo_url
    if data.banner_url is not None:
        college.banner_url = data.banner_url
    if data.settings is not None:
        college.settings = data.settings

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
        "message": "Institutional settings updated successfully.",
    }
